"""Configuration validation for API key.

Note: Model validation is NOT performed here. Users can use any model.
The SUPPORTED_*_MODELS lists are only used for UI suggestions/recommendations.
"""

from __future__ import annotations

import os


def validate_or_raise(
    model: str | None, embedding_model: str | None, api_key: str | None
) -> None:
    """Validate OpenAI API key is configured.

    Note: Model names are NOT validated. Users can use any model supported
    by their provider (OpenAI, OpenRouter, Ollama, etc.).
    """
    # Model validation removed - any model is allowed
    # SUPPORTED_*_MODELS are only for UI suggestions

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OPENAI_API_KEY is required for OpenAI models. Configure it in .agentsmithy/config.json "
            "under 'providers.openai.api_key' or via env OPENAI_API_KEY."
        )
