"""
Ten31 Thoughts - Provider-backed ChromaDB Embedding Function

Routes embeddings through the configured LLM provider (e.g. vLLM on DGX Spark)
instead of ChromaDB's built-in default (all-MiniLM-L6-v2).

Resolution mirrors LLMRouter._default_config: reads store.json → env vars,
picks the embedding model + provider + base URL, and calls the OpenAI-compatible
/v1/embeddings endpoint via litellm.embedding (synchronous).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import litellm
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

logger = logging.getLogger(__name__)

# Same path used by LLMRouter
STORE_JSON_PATH = Path("/data/store.json")

# Maximum texts per embedding call to avoid overloading the endpoint
EMBEDDING_BATCH_SIZE = 64


class ConfiguredEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    ChromaDB EmbeddingFunction backed by the configured LLM provider.

    Reads the same config chain as LLMRouter (store.json → env vars) and calls
    the provider's OpenAI-compatible /v1/embeddings endpoint via litellm.

    Raises ConfigurationError if the provider has no embeddings endpoint
    (e.g. Anthropic).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Args:
            model: Override embedding model name. If None, resolved from config.
            api_base: Override API base URL. If None, resolved from config.
            api_key: Override API key. If None, resolved from config.
        """
        if model and api_base and api_key:
            # All overrides provided — skip config resolution entirely
            resolved = {"model": model, "api_base": api_base, "api_key": api_key}
        else:
            resolved = self._resolve_config()
        self._model = model or resolved["model"]
        self._api_base = api_base or resolved["api_base"]
        self._api_key = api_key or resolved["api_key"]

        if not self._model:
            raise ConfigurationError(
                "No embedding model configured. Set 'embeddingModel' in the "
                "Configure LLM action or TEN31_LLM_EMBEDDING_MODEL env var."
            )

        logger.info(
            f"Embedding function configured: model={self._model}, "
            f"api_base={self._api_base or '(provider default)'}"
        )

    @staticmethod
    def _load_store() -> dict:
        """Load store.json, return empty dict on failure."""
        if STORE_JSON_PATH.exists():
            try:
                with open(STORE_JSON_PATH) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read store.json: {e}")
        return {}

    @classmethod
    def _resolve_config(cls) -> dict:
        """
        Resolve embedding provider config.

        Priority: store.json → environment → defaults.
        Mirrors LLMRouter._default_config for the 'embedding' task.
        """
        store = cls._load_store()

        provider = store.get("provider", "anthropic")
        model = (
            store.get("embeddingModel")
            or os.getenv("TEN31_LLM_EMBEDDING_MODEL", "")
        )
        api_base = None
        api_key = None

        if provider == "vllm":
            api_base = (
                store.get("vllmBaseUrl")
                or os.getenv("VLLM_BASE_URL", "")
            )
            api_key = "vllm"  # litellm needs a non-empty key
            # vLLM is OpenAI-compatible — prefix for litellm routing
            if model and not model.startswith("openai/"):
                model = f"openai/{model}"
        elif provider == "ollama":
            api_base = (
                store.get("ollamaBaseUrl")
                or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            )
            api_key = "ollama"
        elif provider == "openai":
            api_key = (
                store.get("openaiApiKey")
                or os.getenv("OPENAI_API_KEY", "")
            )
            api_base = (
                store.get("openaiBaseUrl")
                or os.getenv("OPENAI_BASE_URL", "")
                or None
            )
        elif provider == "anthropic":
            raise ConfigurationError(
                f"Provider '{provider}' does not support embeddings. "
                "Configure a provider with an /v1/embeddings endpoint "
                "(vllm, ollama, or openai) for embedding tasks."
            )
        else:
            # Unknown provider — try openai-compatible if a base URL exists
            api_base = (
                store.get("vllmBaseUrl")
                or store.get("openaiBaseUrl")
                or os.getenv("VLLM_BASE_URL", "")
                or os.getenv("OPENAI_BASE_URL", "")
                or None
            )
            api_key = "default"

        return {
            "model": model,
            "api_base": api_base or None,
            "api_key": api_key,
        }

    def __call__(self, input: Documents) -> Embeddings:
        """
        Embed a batch of documents.

        Batches large inputs to avoid overloading the endpoint.
        Raises EmbeddingError on failure — never silently falls back.
        """
        if not input:
            return []

        all_embeddings: Embeddings = []

        for i in range(0, len(input), EMBEDDING_BATCH_SIZE):
            batch = input[i : i + EMBEDDING_BATCH_SIZE]
            embeddings = self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the provider's embedding endpoint for a single batch."""
        kwargs = {
            "model": self._model,
            "input": texts,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base

        try:
            response = litellm.embedding(**kwargs)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            raise EmbeddingError(
                f"Embedding call failed (model={self._model}, "
                f"api_base={self._api_base}): {e}"
            ) from e


class ConfigurationError(Exception):
    """Raised when the embedding provider is misconfigured."""
    pass


class EmbeddingError(Exception):
    """Raised when an embedding call fails."""
    pass
