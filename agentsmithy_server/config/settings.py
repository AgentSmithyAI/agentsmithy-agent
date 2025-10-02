"""Configuration settings for AgentSmithy server.

This module provides a Settings class that wraps the ConfigManager,
providing property-based access to configuration values with hot-reload support.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentsmithy_server.config.manager import ConfigManager


class Settings:
    """Application settings with hot-reload support.

    This class wraps ConfigManager and provides property-based access
    to configuration values. It supports both ConfigManager and environment
    variable fallbacks for backwards compatibility.
    """

    def __init__(self, config_manager: ConfigManager | None = None):
        self._config_manager = config_manager

    # Validation helper
    def validate_or_raise(self) -> None:
        from agentsmithy_server.config.validation import validate_or_raise as _v

        _v(self.model, self.embedding_model, self.openai_api_key)

    def _get(
        self,
        key: str,
        default: str | int | float | bool | None,
        env_key: str | None = None,
    ):
        """Get config value from manager, fallback to env, then default."""
        if self._config_manager:
            return self._config_manager.get(key, default)
        # Fallback to environment variable
        if env_key and (env_val := os.getenv(env_key)):
            # Type conversion based on default type
            if isinstance(default, bool):
                return env_val.lower() in ("true", "1", "yes")
            elif isinstance(default, int):
                return int(env_val)
            elif isinstance(default, float):
                return float(env_val)
            return env_val
        return default

    # OpenAI Configuration
    @property
    def openai_api_key(self) -> str | None:
        return self._get("openai_api_key", None, "OPENAI_API_KEY")

    # Server Configuration
    @property
    def server_host(self) -> str:
        return self._get("server_host", "localhost", "SERVER_HOST")

    @property
    def server_port(self) -> int:
        return self._get("server_port", 11434, "SERVER_PORT")

    # RAG Configuration
    @property
    def chroma_persist_directory(self) -> str:
        return self._get(
            "chroma_persist_directory", "./chroma_db", "CHROMA_PERSIST_DIRECTORY"
        )

    @property
    def max_context_length(self) -> int:
        return self._get("max_context_length", 10000, "MAX_CONTEXT_LENGTH")

    @property
    def max_open_files(self) -> int:
        return self._get("max_open_files", 5, "MAX_OPEN_FILES")

    # Summarization
    @property
    def summary_trigger_token_budget(self) -> int:
        return self._get(
            "summary_trigger_token_budget", 20000, "SUMMARY_TRIGGER_TOKEN_BUDGET"
        )

    # LLM Configuration
    @property
    def model(self) -> str:
        return self._get("model", "gpt-5", "MODEL")

    @property
    def temperature(self) -> float:
        return self._get("temperature", 0.7, "TEMPERATURE")

    @property
    def reasoning_effort(self) -> str:
        return self._get("reasoning_effort", "low", "REASONING_EFFORT")

    @property
    def embedding_model(self) -> str:
        return self._get("embedding_model", "text-embedding-3-small", "EMBEDDING_MODEL")

    @property
    def max_tokens(self) -> int:
        return self._get("max_tokens", 4000, "MAX_TOKENS")

    @property
    def streaming_enabled(self) -> bool:
        return self._get("streaming_enabled", True, "STREAMING_ENABLED")

    # Web/HTTP Configuration
    @property
    def web_user_agent(self) -> str:
        default_ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        return self._get("web_user_agent", default_ua, "WEB_USER_AGENT")

    # Logging Configuration
    @property
    def log_level(self) -> str:
        return self._get("log_level", "INFO", "LOG_LEVEL")

    @property
    def log_format(self) -> str:
        return self._get("log_format", "pretty", "LOG_FORMAT")


# Global settings instance (will be initialized with config manager)
settings = Settings()
