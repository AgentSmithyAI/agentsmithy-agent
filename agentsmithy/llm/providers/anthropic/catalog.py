"""Anthropic model catalog provider.

Provides static model catalog for Anthropic Claude models.
Unlike OpenAI, Anthropic doesn't have a public /models endpoint.
"""

from __future__ import annotations

from typing import Any

from agentsmithy.llm.providers.catalog import (
    IModelCatalogProvider,
    ModelCatalog,
)
from agentsmithy.llm.providers.types import Vendor

from .models import SUPPORTED_ANTHROPIC_CHAT_MODELS


class AnthropicModelCatalogProvider(IModelCatalogProvider):
    """Model catalog for Anthropic.

    Returns static list of known Claude models.
    Anthropic doesn't expose a models listing API.
    """

    def vendor(self) -> Vendor:
        return Vendor.ANTHROPIC

    def get_catalog(self, provider_config: dict[str, Any]) -> ModelCatalog:
        """Return static catalog of Anthropic models.

        Args:
            provider_config: Provider configuration (unused for static catalog).

        Returns:
            ModelCatalog with known Claude models.
        """
        return ModelCatalog(
            chat=list(SUPPORTED_ANTHROPIC_CHAT_MODELS),
            embeddings=[],  # Anthropic doesn't have public embedding models
        )


# Singleton instance
anthropic_catalog_provider = AnthropicModelCatalogProvider()
