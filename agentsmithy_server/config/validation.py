"""Configuration validation for supported OpenAI models and API key."""

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
    """Validate configured chat and embedding models and OpenAI API key.

    Rules:
    - model must be one of strictly supported OpenAI chat models
    - embedding_model must be one of strictly supported embedding models
    - OPENAI_API_KEY must be set (via settings or environment)
    """
    m = model or ""
    if m not in SUPPORTED_OPENAI_CHAT_MODELS:
        raise ValueError(
            "Unsupported OpenAI chat model: '" + (model or "") + "'. "
            "Supported: " + _format_options(SUPPORTED_OPENAI_CHAT_MODELS)
        )

    em = embedding_model or ""
    if em not in SUPPORTED_OPENAI_EMBEDDING_MODELS:
        raise ValueError(
            "Unsupported OpenAI embedding model: '" + (embedding_model or "") + "'. "
            "Supported: " + _format_options(SUPPORTED_OPENAI_EMBEDDING_MODELS)
        )

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OPENAI_API_KEY is required for OpenAI models. Configure it in .agentsmithy/config.json "
            "under 'providers.openai.api_key' (preferred), or 'openai.api_key' for legacy, or via env OPENAI_API_KEY."
        )
