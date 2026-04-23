"""
Ten31 Thoughts - LLM Router
Unified interface to multiple LLM providers via LiteLLM.
Supports Claude, OpenAI, Ollama, and any LiteLLM-compatible provider.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import litellm
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Retry decorator for transient connection errors
# Retries up to 3 times with exponential backoff (1s, 2s, 4s)
llm_retry = retry(
    retry=retry_if_exception_type((
        litellm.APIConnectionError,
        litellm.RateLimitError,
        litellm.ServiceUnavailableError,
    )),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# StartOS store.json path for LLM configuration
STORE_JSON_PATH = Path("/data/store.json")


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

    def _load_store(self) -> dict:
        """Load LLM config from StartOS store.json, fallback to env vars."""
        if STORE_JSON_PATH.exists():
            try:
                with open(STORE_JSON_PATH) as f:
                    store = json.load(f)
                    logger.info(f"Loaded LLM config from {STORE_JSON_PATH}")
                    return store
            except Exception as e:
                logger.warning(f"Failed to read store.json: {e}")
        return {}

    def _default_config(self) -> dict[str, LLMConfig]:
        """Build default config from store.json or environment variables."""
        store = self._load_store()

        # Prefer store.json, fallback to env vars
        provider = store.get("provider", "anthropic")
        anthropic_key = store.get("anthropicApiKey") or os.getenv("ANTHROPIC_API_KEY")
        openai_key = store.get("openaiApiKey") or os.getenv("OPENAI_API_KEY")
        openai_base = store.get("openaiBaseUrl") or os.getenv("OPENAI_BASE_URL", "")
        ollama_base = store.get("ollamaBaseUrl") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        vllm_base = store.get("vllmBaseUrl") or os.getenv("VLLM_BASE_URL", "")

        # Model overrides from store
        model_overrides = {
            "analysis": store.get("analysisModel"),
            "synthesis": store.get("synthesisModel"),
            "chat": store.get("chatModel"),
            "embedding": store.get("embeddingModel"),
        }

        configs = {}

        for task, default_model in DEFAULT_MODELS.items():
            # Priority: store.json > env var > default
            model = model_overrides.get(task) or os.getenv(f"TEN31_LLM_{task.upper()}_MODEL", default_model)

            config = LLMConfig(model=model)

            # Route based on selected provider first, then auto-detect from model name
            if provider == "vllm":
                # vLLM is OpenAI-compatible — use openai/ prefix for LiteLLM
                if not model.startswith("openai/"):
                    config.model = f"openai/{model}"
                config.api_base = vllm_base
                config.api_key = "vllm"  # LiteLLM needs a non-empty key
            elif provider == "ollama" or "ollama" in model or model.startswith("ollama/"):
                config.api_base = ollama_base
                config.api_key = "ollama"  # LiteLLM needs a non-empty key
            elif provider == "openai" or "gpt" in model or "o1" in model or "text-embedding" in model:
                config.api_key = openai_key
                if openai_base:
                    config.api_base = openai_base
            elif provider == "anthropic" or "claude" in model or "anthropic" in model:
                config.api_key = anthropic_key
            else:
                # Unknown — try to auto-detect from model name
                if "claude" in model or "anthropic" in model:
                    config.api_key = anthropic_key
                elif "gpt" in model or "o1" in model or "text-embedding" in model:
                    config.api_key = openai_key

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
            response = await self._call_completion(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed for task={task}, model={config.model}: {e}")
            raise

    async def complete_with_tools(
        self,
        task: str,
        messages: list[dict],
        tools: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
    ) -> dict:
        """
        Send a completion request with tool/function calling support.

        Args:
            task: Task type ("analysis", "synthesis", "chat")
            messages: List of message dicts
            tools: List of tool definitions (OpenAI function calling format)
            temperature: Override default temperature
            max_tokens: Override default max tokens
            system: System prompt

        Returns:
            Dict with "content" (str or None) and "tool_calls" (list or None).
        """
        config = self.config.get(task)
        if not config:
            raise ValueError(f"No LLM configuration for task: {task}")

        final_messages = messages.copy()
        if system:
            final_messages = [{"role": "system", "content": system}] + final_messages

        kwargs = {
            "model": config.model,
            "messages": final_messages,
            "temperature": temperature if temperature is not None else config.temperature,
            "max_tokens": max_tokens or config.max_tokens,
            "tools": tools,
        }

        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.api_base:
            kwargs["api_base"] = config.api_base

        try:
            response = await self._call_completion(**kwargs)
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": None,
            }
            
            # Extract tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message.tool_calls
                ]
            
            return result
        except Exception as e:
            logger.error(f"LLM call with tools failed for task={task}, model={config.model}: {e}")
            raise

    @llm_retry
    async def _call_completion(self, **kwargs):
        """Internal method with retry wrapper for litellm.acompletion."""
        return await litellm.acompletion(**kwargs)

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
            response = await self._call_embedding(**kwargs)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error(f"Embedding call failed: {e}")
            raise

    @llm_retry
    async def _call_embedding(self, **kwargs):
        """Internal method with retry wrapper for litellm.aembedding."""
        return await litellm.aembedding(**kwargs)

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
