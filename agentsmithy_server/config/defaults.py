"""Default configuration values for AgentSmithy."""

from typing import Any


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    return {
        # Note: legacy top-level 'openai' section removed from defaults.
        # Generic providers section to hold credentials/config per vendor
        "providers": {
            "openai": {
                "api_key": None,
                "base_url": None,
                # Provider-wide extension options; mapped appropriately per model family
                "options": {},
            },
            "llama": {
                "model_path": None,
                "n_ctx": 8192,
                "n_threads": 8,
                "temperature": 0.1,
                "max_tokens": 4000,
                "verbose": False,
            }
        },
        # Note: legacy flat keys (openai_api_key, openai_base_url) are not in defaults.
        # They are still read via Settings for backward compatibility if present in config/env.
        # Server Configuration
        "server_host": "localhost",
        "server_port": 11434,
        # RAG Configuration
        "chroma_persist_directory": "./chroma_db",
        "max_context_length": 10000,
        "max_open_files": 5,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # Models configuration (canonical)
        "models": {
            "agents": {
                "universal": {"model": "gpt-5"},
                "inspector": {"model": "gpt-5-mini"},
            },
            "embeddings": {"model": "text-embedding-3-small"},
        },
        # Streaming toggle
        "streaming_enabled": True,
        # Web/HTTP Configuration
        "web_user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        # Logging Configuration
        "log_level": "INFO",
        "log_format": "pretty",
    }
