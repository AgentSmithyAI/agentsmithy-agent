"""Default configuration values for AgentSmithy."""

from typing import Any


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    return {
        # Server Configuration
        "server_host": "localhost",
        "server_port": 11434,
        # RAG Configuration
        "chroma_persist_directory": "./chroma_db",
        "max_context_length": 10000,
        "max_open_files": 5,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # Web/HTTP Configuration
        "web_user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        # Logging Configuration
        "log_level": "INFO",
        "log_format": "pretty",
        # Providers Configuration
        "providers": {
            "openai": {
                "api_key": None,
                "base_url": None,
                "temperature": 0.7,
                "max_tokens": 4000,
                "reasoning_effort": "low",
            },
            "llama": {
                "base_url": "http://localhost:8000/v1",
                "api_key": "not-needed",
                "temperature": 0.7,
                "max_tokens": 1024,
            },
        },
        # Models Configuration (agents and embeddings)
        "models": {
            "agent": {
                "inspector": "gpt-5",  # Default OpenAI model
                "universal": "gpt-5",  # Default OpenAI model
            },
            "embedding": "text-embedding-3-small",  # Default OpenAI embedding
        },
    }
