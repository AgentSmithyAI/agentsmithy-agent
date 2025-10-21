"""Default configuration values for AgentSmithy."""

from typing import Any


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    return {
        # Provider definitions - each provider is a complete configuration
        # including type, model, credentials, and options
        "providers": {
            "gpt5": {
                "type": "openai",
                "model": "gpt-5",
                "api_key": None,
                "base_url": None,
                "options": {},
            },
            "gpt5-mini": {
                "type": "openai",
                "model": "gpt-5-mini",
                "api_key": None,
                "base_url": None,
                "options": {},
            },
            "gpt4o-mini": {
                "type": "openai",
                "model": "gpt-4o-mini",
                "api_key": None,
                "base_url": None,
                "options": {},
            },
            "embeddings": {
                "type": "openai",
                "model": "text-embedding-3-small",
                "api_key": None,
                "base_url": None,
                "options": {},
            },
            # Example: Local OpenAI-compatible server (Ollama)
            # "gpt-local": {
            #     "type": "openai",
            #     "model": "gpt-oss:20b",
            #     "api_key": None,
            #     "base_url": "http://localhost:11434/v1",
            #     "options": {},
            # }
        },
        # Note: legacy flat keys (openai_api_key, openai_base_url) are not in defaults.
        # They are still read via Settings for backward compatibility if present in config/env.
        # Server Configuration
        "server_host": "localhost",
        "server_port": 8765,
        # RAG Configuration
        "chroma_persist_directory": "./chroma_db",
        "max_context_length": 10000,
        "max_open_files": 5,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # Models configuration - references to provider definitions
        "models": {
            "agents": {
                "universal": {"provider": "gpt5"},
                "inspector": {"provider": "gpt5-mini"},
            },
            "embeddings": {"provider": "embeddings"},
            "summarization": {"provider": "gpt4o-mini"},
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
