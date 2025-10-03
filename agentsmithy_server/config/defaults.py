"""Default configuration values for AgentSmithy."""

from typing import Any


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    return {
        # OpenAI Configuration
        "openai_api_key": None,
        "openai_base_url": None,  # e.g., "http://localhost:1234/v1" for local servers
        # Server Configuration
        "server_host": "localhost",
        "server_port": 11434,
        # RAG Configuration
        "chroma_persist_directory": "./chroma_db",
        "max_context_length": 10000,
        "max_open_files": 5,
        # Summarization
        "summary_trigger_token_budget": 20000,
        # LLM Configuration
        "model": "gpt-5",
        "temperature": 0.7,
        "reasoning_effort": "low",
        "embedding_model": "text-embedding-3-small",
        "max_tokens": 4000,
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
