"""
Ten31 Thoughts - LLM Router
Unified interface to multiple LLM providers via LiteLLM.
Supports Claude, OpenAI, Ollama, and any LiteLLM-compatible provider.
"""

import logging
import os
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None  # For Ollama or custom endpoints
    max_tokens: int = 4096
    temperature: float = 0.3


# Default model assignments per task type
DEFAULT_MODELS = {
    "analysis": "claude-sonnet-4-20250514",
    "synthesis": "claude-sonnet-4-20250514",
    "chat": "claude-sonnet-4-20250514",
    "embedding": "text-embedding-3-small",
}


class LLMRouter:
    """
    Routes LLM calls to the appropriate provider based on task type.
    Uses LiteLLM for unified API across providers.
    """

    def __init__(self, config: Optional[dict[str, LLMConfig]] = None):
        """
        Args:
            config: Dict mapping task types to LLMConfig.
                    Keys: "analysis", "synthesis", "chat", "embedding"
        """
        self.config = config or self._default_config()

    def _default_config(self) -> dict[str, LLMConfig]:
        """Build default config from environment variables."""
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        configs = {}

        for task, default_model in DEFAULT_MODELS.items():
            model = os.getenv(f"TEN31_LLM_{task.upper()}_MODEL", default_model)

            config = LLMConfig(model=model)

            # Auto-detect provider from model name and set keys
            if "claude" in model or "anthropic" in model:
                config.api_key = anthropic_key
            elif "gpt" in model or "o1" in model or "text-embedding" in model:
                config.api_key = openai_key
            elif "ollama" in model or model.startswith("ollama/"):
                config.api_base = ollama_base
                config.api_key = "ollama"  # LiteLLM needs a non-empty key

            configs[task] = config

        return configs

    async def complete(
        self,
        task: str,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> str:
        """
        Send a completion request to the appropriate LLM.

        Args:
            task: Task type ("analysis", "synthesis", "chat")
            messages: List of message dicts with "role" and "content"
            temperature: Override default temperature
            max_tokens: Override default max tokens
            system: System prompt

        Returns:
            The model's response text.
        """
        import litellm

        config = self.config.get(task)
        if not config:
            raise ValueError(f"No LLM configuration for task: {task}")

        kwargs = {
            "model": config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else config.temperature,
            "max_tokens": max_tokens or config.max_tokens,
        }

        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.api_base:
            kwargs["api_base"] = config.api_base
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + messages

        try:
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed for task={task}, model={config.model}: {e}")
            raise

    async def complete_json(
        self,
        task: str,
        messages: list[dict],
        system: Optional[str] = None,
    ) -> dict:
        """
        Send a completion request expecting JSON output.
        Parses the response and returns a dict.
        """
        import json

        full_system = (system or "") + (
            "\n\nYou MUST respond with valid JSON only. "
            "No markdown code fences, no preamble, no explanation. "
            "Just the JSON object."
        )

        text = await self.complete(
            task=task,
            messages=messages,
            system=full_system.strip(),
            temperature=0.1,
        )

        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nResponse: {text[:500]}")
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.
        Uses the 'embedding' task configuration.
        """
        import litellm

        config = self.config.get("embedding")
        if not config:
            raise ValueError("No embedding model configured")

        kwargs = {
            "model": config.model,
            "input": texts,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.api_base:
            kwargs["api_base"] = config.api_base

        try:
            response = await litellm.aembedding(**kwargs)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error(f"Embedding call failed: {e}")
            raise

    def get_model_info(self) -> dict:
        """Return current model assignments for each task."""
        return {
            task: {
                "model": config.model,
                "has_api_key": bool(config.api_key),
                "api_base": config.api_base,
            }
            for task, config in self.config.items()
        }
