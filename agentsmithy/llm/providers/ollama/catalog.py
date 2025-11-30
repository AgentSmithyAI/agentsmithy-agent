"""Ollama model catalog provider.

Dynamically fetches available models from Ollama server via API.
"""

from __future__ import annotations

from typing import Any

import httpx

from agentsmithy.llm.providers.catalog import (
    IModelCatalogProvider,
    ModelCatalog,
)
from agentsmithy.llm.providers.types import Vendor


class OllamaModelCatalogProvider(IModelCatalogProvider):
    """Model catalog for Ollama.

    Dynamically queries Ollama server for available models.
    Returns empty catalog if server is not running or any error occurs.
    """

    def vendor(self) -> Vendor:
        return Vendor.OLLAMA

    def get_catalog(self, provider_config: dict[str, Any]) -> ModelCatalog:
        """Fetch models from Ollama server.

        Args:
            provider_config: Must contain 'base_url' for Ollama server.

        Returns:
            ModelCatalog with available models, or empty on error.
        """
        models = self._fetch_models(provider_config)
        if not models:
            return ModelCatalog()
        return ModelCatalog(chat=models)

    def _fetch_models(self, provider_config: dict[str, Any]) -> list[str]:
        """Fetch available models from Ollama server.

        Returns empty list if Ollama is not configured, not running,
        or any error occurs.
        """
        base_url = provider_config.get("base_url")
        if not base_url:
            return []

        # Ollama API endpoint for listing models
        # base_url is usually "http://localhost:11434/v1" (OpenAI-compatible)
        # but /api/tags is on the root, so strip /v1 if present
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        tags_url = f"{base}/api/tags"

        try:
            # Quick timeout - don't block if Ollama is down
            with httpx.Client(timeout=2.0) as client:
                response = client.get(tags_url)
                if response.status_code != 200:
                    return []
                data = response.json()
                models = data.get("models", [])
                return [m.get("name", "") for m in models if m.get("name")]
        except Exception:
            # Ollama not running, network error, timeout, etc.
            return []


# Singleton instance
ollama_catalog_provider = OllamaModelCatalogProvider()
