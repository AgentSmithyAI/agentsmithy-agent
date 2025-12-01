"""Providers package.

Exposes helper to register built-in provider adapters and catalog providers.
"""

from .anthropic.adapter import factory as anthropic_factory
from .anthropic.catalog import anthropic_catalog_provider
from .catalog import register_catalog_provider
from .ollama.catalog import ollama_catalog_provider
from .openai.adapter import factory as openai_factory
from .openai.catalog import openai_catalog_provider
from .registry import register_adapter_factory

_CATALOG_REGISTERED = False


def register_builtin_adapters() -> None:
    """Register built-in adapters (idempotent)."""
    register_adapter_factory(openai_factory)
    register_adapter_factory(anthropic_factory)


def register_builtin_catalog_providers() -> None:
    """Register built-in model catalog providers (idempotent)."""
    global _CATALOG_REGISTERED
    if _CATALOG_REGISTERED:
        return
    register_catalog_provider(openai_catalog_provider)
    register_catalog_provider(ollama_catalog_provider)
    register_catalog_provider(anthropic_catalog_provider)
    _CATALOG_REGISTERED = True
