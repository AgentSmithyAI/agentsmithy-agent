"""Configuration validation for supported models and API keys across all vendors."""

from __future__ import annotations

import os
from collections.abc import Iterable

from agentsmithy_server.core.providers.openai.models import (
    SUPPORTED_OPENAI_CHAT_MODELS,
    SUPPORTED_OPENAI_EMBEDDING_MODELS,
)


def _format_options(options: Iterable[str]) -> str:
    # Convert to list to ensure we can sort it (handles lazy iterables)
    return ", ".join(sorted(list(options)))


def validate_or_raise(
    model: str | None, embedding_model: str | None, api_key: str | None
) -> None:
    """Validate configured chat and embedding models and API keys.

    This validation now supports multiple vendors (OpenAI, llama/OTHER, etc.)
    by checking through the provider registry.

    Rules:
    - model must be supported by a registered provider adapter
    - embedding_model validation is relaxed for non-OpenAI vendors
    - API key is only required for OpenAI vendor
    """
    if not model:
        raise ValueError("Model must be specified in configuration")

    # Try to resolve model through provider registry
    from agentsmithy_server.core.providers import register_builtin_adapters
    from agentsmithy_server.core.providers.registry import get_adapter
    from agentsmithy_server.core.providers.types import Vendor

    register_builtin_adapters()

    try:
        adapter = get_adapter(model)
        vendor = adapter.vendor()
    except ValueError as e:
        # Model not found in any provider
        raise ValueError(
            f"Unsupported model: '{model}'. "
            f"Model not recognized by any registered provider. "
            f"Error: {e}"
        ) from e

    # Vendor-specific validation
    if vendor == Vendor.OPENAI:
        # Strict validation for OpenAI models
        if model not in SUPPORTED_OPENAI_CHAT_MODELS:
            raise ValueError(
                f"Unsupported OpenAI chat model: '{model}'. "
                f"Supported: {_format_options(SUPPORTED_OPENAI_CHAT_MODELS)}"
            )

        # Check embedding model for OpenAI
        if embedding_model and embedding_model not in SUPPORTED_OPENAI_EMBEDDING_MODELS:
            raise ValueError(
                f"Unsupported OpenAI embedding model: '{embedding_model}'. "
                f"Supported: {_format_options(SUPPORTED_OPENAI_EMBEDDING_MODELS)}"
            )

        # Require API key for OpenAI
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI models. "
                "Set it in .agentsmithy/config.json as 'openai_api_key' "
                "or via environment variable OPENAI_API_KEY."
            )
    elif vendor == Vendor.OTHER:
        # Relaxed validation for OTHER/llama models
        # No API key required
        # Embedding model validation is relaxed (any model name is ok)
        pass
    # Other vendors can be added here as needed
