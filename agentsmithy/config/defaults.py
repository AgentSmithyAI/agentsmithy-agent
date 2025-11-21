"""Default configuration values for AgentSmithy."""

from typing import Any


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
        "workloads": {
            "reasoning": {
                "provider": "openai",
                "model": "gpt-5.1-codex",
                "options": {},
            },
            "execution": {
                "provider": "openai",
                "model": "gpt-5.1-codex-mini",
                "options": {},
            },
            "summarization": {
                "provider": "openai",
                "model": "gpt-5.1-codex-mini",
                "options": {},
            },
            "embeddings": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "options": {},
            },
            "inspector": {
                "provider": "openai",
                "model": "gpt-5.1-codex-mini",
                "options": {},
            },
        },
        # Note: legacy flat keys (openai_api_key, openai_base_url) are not in defaults.
        # They are still read via Settings for backward compatibility if present in config/env.
        # Server Configuration
        "server_host": "localhost",
        "server_port": 8765,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # Models configuration - references to provider definitions
        "models": {
            "agents": {
                "universal": {"workload": "reasoning"},
                "inspector": {"workload": "inspector"},
            },
            "embeddings": {"workload": "embeddings"},
            "summarization": {"workload": "summarization"},
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
