"""OpenAI model catalog provider.

Tries to fetch models dynamically via OpenAI API, falls back to static list.
"""

from __future__ import annotations

from typing import Any

import httpx

from agentsmithy.llm.providers.catalog import (
    IModelCatalogProvider,
    ModelCatalog,
)
from agentsmithy.llm.providers.types import Vendor

# Known model patterns for classification
# OpenAI API doesn't tell us which models are chat vs embeddings
CHAT_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "chatgpt-")
EMBEDDING_MODEL_PREFIXES = ("text-embedding-",)

# Models to exclude (fine-tuned, deprecated, internal)
EXCLUDED_PATTERNS = (
    "ft:",  # fine-tuned
    "davinci",  # old completions
    "curie",
    "babbage",
    "ada",
    "whisper",  # audio
    "tts",  # text-to-speech
    "dall-e",  # images
    "canary",  # internal
    "realtime",  # realtime API
)


class OpenAIModelCatalogProvider(IModelCatalogProvider):
    """Model catalog for OpenAI.

    Tries to fetch available models from OpenAI API.
    Falls back to static registry if API call fails.
    """

    def vendor(self) -> Vendor:
        return Vendor.OPENAI

    def get_catalog(self, provider_config: dict[str, Any]) -> ModelCatalog:
        """Return OpenAI models, trying API first, then static fallback."""
        # Try dynamic fetch if we have credentials
        api_key = provider_config.get("api_key")
        base_url = provider_config.get("base_url", "https://api.openai.com/v1")

        if api_key:
            dynamic_catalog = self._fetch_models_from_api(api_key, base_url)
            if not dynamic_catalog.is_empty():
                return dynamic_catalog

        # Fallback to static list
        return self._get_static_catalog()

    def _fetch_models_from_api(self, api_key: str, base_url: str) -> ModelCatalog:
        """Fetch models from OpenAI /v1/models endpoint."""
        base = base_url.rstrip("/")
        models_url = f"{base}/models"

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if response.status_code != 200:
                    return ModelCatalog()

                data = response.json()
                models = data.get("data", [])

                chat_models: list[str] = []
                embedding_models: list[str] = []

                for model in models:
                    model_id = model.get("id", "")
                    if not model_id:
                        continue

                    # Skip excluded models
                    if any(pat in model_id.lower() for pat in EXCLUDED_PATTERNS):
                        continue

                    # Classify by prefix
                    if any(model_id.startswith(p) for p in CHAT_MODEL_PREFIXES):
                        chat_models.append(model_id)
                    elif any(model_id.startswith(p) for p in EMBEDDING_MODEL_PREFIXES):
                        embedding_models.append(model_id)

                return ModelCatalog(
                    chat=sorted(chat_models),
                    embeddings=sorted(embedding_models),
                )
        except Exception:
            return ModelCatalog()

    def _get_static_catalog(self) -> ModelCatalog:
        """Return static model list from registry."""
        try:
            from agentsmithy.llm.providers.openai.models import (
                SUPPORTED_OPENAI_CHAT_MODELS,
                SUPPORTED_OPENAI_EMBEDDING_MODELS,
            )

            return ModelCatalog(
                chat=list(SUPPORTED_OPENAI_CHAT_MODELS),
                embeddings=list(SUPPORTED_OPENAI_EMBEDDING_MODELS),
            )
        except Exception:
            return ModelCatalog()


# Singleton instance
openai_catalog_provider = OpenAIModelCatalogProvider()
