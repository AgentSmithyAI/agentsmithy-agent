"""Default configuration values for AgentSmithy."""

from typing import Any


def _build_default_workloads() -> dict[str, Any]:
    """Build workloads from model catalog - one workload per model.

    Workloads are named by model name (e.g., "gpt-5.1-codex", "text-embedding-3-small").
    This allows easy switching between models in the config.

    When new models are added to the catalog, they automatically appear
    as available workloads for all users via config merge.

    Note: 'kind' field is not set explicitly in defaults - it will be
    auto-detected from the model name when building metadata.
    """
    workloads: dict[str, Any] = {}

    try:
        from agentsmithy.llm.providers.openai.models import (
            SUPPORTED_OPENAI_CHAT_MODELS,
            SUPPORTED_OPENAI_EMBEDDING_MODELS,
        )

        # Chat models → workloads (kind will be auto-detected as "chat")
        for model in SUPPORTED_OPENAI_CHAT_MODELS:
            workloads[model] = {
                "provider": "openai",
                "model": model,
                "options": {},
            }

        # Embedding models → workloads (kind will be auto-detected as "embeddings")
        for model in SUPPORTED_OPENAI_EMBEDDING_MODELS:
            workloads[model] = {
                "provider": "openai",
                "model": model,
                "options": {},
            }
    except ImportError:
        # Fallback if import fails (shouldn't happen in normal operation)
        pass

    # TODO: Add Anthropic, Google, xAI model catalogs when implemented

    return workloads


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    return {
        # Provider definitions - each provider is a complete configuration
        # including type, model, credentials, and options
        "providers": {
            # Shared OpenAI credentials (default for all workloads)
            "openai": {
                "type": "openai",
                "api_key": None,
                "base_url": "https://api.openai.com/v1",
                "options": {},
            },
        },
        # Workloads auto-generated from model catalog
        # Each workload is named by its model (e.g., "gpt-5.1-codex")
        "workloads": _build_default_workloads(),
        # Note: legacy flat keys (openai_api_key, openai_base_url) are not in defaults.
        # They are still read via Settings for backward compatibility if present in config/env.
        # Server Configuration
        "server_host": "localhost",
        "server_port": 8765,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # Models configuration - references workloads by model name
        "models": {
            "agents": {
                "universal": {"workload": "gpt-5.1-codex"},
                "inspector": {"workload": "gpt-5.1-codex-mini"},
            },
            "embeddings": {"workload": "text-embedding-3-small"},
            "summarization": {"workload": "gpt-5.1-codex-mini"},
        },
        # Web/HTTP Configuration
        "web_user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        # Logging Configuration
        "log_level": "INFO",
        "log_format": "pretty",
        "log_colors": True,
    }
