"""Model catalog interface and registry.

Provides a unified way for providers to expose their available models.
Each provider implements IModelCatalogProvider to return its model catalog.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import Vendor


class ModelCatalog:
    """Model catalog for a single provider."""

    def __init__(
        self,
        chat: list[str] | None = None,
        embeddings: list[str] | None = None,
    ):
        self.chat = sorted(chat) if chat else []
        self.embeddings = sorted(embeddings) if embeddings else []

    def to_dict(self) -> dict[str, list[str]]:
        """Convert to dict for API response."""
        return {
            "chat": self.chat,
            "embeddings": self.embeddings,
        }

    def is_empty(self) -> bool:
        """Check if catalog has no models."""
        return not self.chat and not self.embeddings


class IModelCatalogProvider(ABC):
    """Interface for provider-specific model catalog.

    Each provider implements this to expose its available models.
    """

    @abstractmethod
    def vendor(self) -> Vendor:
        """Return the vendor type this provider handles."""
        pass

    @abstractmethod
    def get_catalog(self, provider_config: dict[str, Any]) -> ModelCatalog:
        """Return available models for this provider.

        Args:
            provider_config: Provider configuration from config file,
                             including base_url, api_key, etc.

        Returns:
            ModelCatalog with available chat and embedding models.
            Returns empty catalog on errors (server down, etc).
        """
        pass


# Registry of catalog providers
_CATALOG_PROVIDERS: dict[Vendor, IModelCatalogProvider] = {}


def register_catalog_provider(provider: IModelCatalogProvider) -> None:
    """Register a model catalog provider."""
    _CATALOG_PROVIDERS[provider.vendor()] = provider


def get_catalog_provider(vendor: Vendor) -> IModelCatalogProvider | None:
    """Get catalog provider for a vendor."""
    return _CATALOG_PROVIDERS.get(vendor)


def build_full_model_catalog(providers: dict[str, Any]) -> dict[str, Any]:
    """Build complete model catalog from all configured providers.

    Args:
        providers: Dict of provider configs from config file.

    Returns:
        Dict mapping vendor name to model catalog.
    """
    catalog: dict[str, Any] = {}

    # Group provider configs by vendor type
    vendor_configs: dict[Vendor, dict[str, Any]] = {}
    for _name, provider_cfg in providers.items():
        if not isinstance(provider_cfg, dict):
            continue
        vendor_type = provider_cfg.get("type", Vendor.OPENAI.value)
        try:
            vendor = Vendor(vendor_type)
        except ValueError:
            continue
        # Use first config for each vendor type
        if vendor not in vendor_configs:
            vendor_configs[vendor] = provider_cfg

    # Get catalog from each registered provider
    for vendor, provider_cfg in vendor_configs.items():
        catalog_provider = get_catalog_provider(vendor)
        if catalog_provider:
            models = catalog_provider.get_catalog(provider_cfg)
            if not models.is_empty():
                catalog[vendor.value] = models.to_dict()

    # Also include vendors with static catalogs even if not configured
    for vendor, catalog_provider in _CATALOG_PROVIDERS.items():
        if vendor.value not in catalog:
            # Try with empty config (for static catalogs like OpenAI)
            models = catalog_provider.get_catalog({})
            if not models.is_empty():
                catalog[vendor.value] = models.to_dict()

    return catalog
