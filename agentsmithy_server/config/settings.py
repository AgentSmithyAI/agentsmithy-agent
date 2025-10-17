"""Configuration settings for AgentSmithy server.

This module provides a Settings class that wraps the ConfigManager,
providing property-based access to configuration values with hot-reload support.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

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
        default: Any,
        env_key: str | None = None,
    ) -> Any:
        """Get config value from manager, fallback to env, then default."""
        if self._config_manager:
            # Support dot-path lookup for nested sections
            if "." in key:
                try:
                    cfg_any: object = self._config_manager.get_all()
                    cfg_obj = cfg_any
                    for part in key.split("."):
                        if isinstance(cfg_obj, dict) and part in cfg_obj:
                            cfg_obj = cfg_obj[part]
                        else:
                            cfg_obj = default
                            break
                    return cfg_obj
                except Exception:
                    return default
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
        # Canonical: providers.openai.api_key; fallback to env only
        prov = self.get_provider_config("openai")
        if isinstance(prov, dict) and prov.get("api_key"):
            return prov.get("api_key")
        return self._get("OPENAI_API_KEY", None, "OPENAI_API_KEY")

    @property
    def openai_base_url(self) -> str | None:
        prov = self.get_provider_config("openai")
        if isinstance(prov, dict) and prov.get("base_url"):
            return prov.get("base_url")
        return self._get("OPENAI_BASE_URL", None, "OPENAI_BASE_URL")

    # OpenAI Chat nested configuration (preferred)
    @property
    def openai_chat_model(self) -> str | None:
        # models.agents.universal overrides global default model
        agents = self._get("models.agents", None)
        if isinstance(agents, dict):
            uni = agents.get("universal")
            if isinstance(uni, dict) and isinstance(uni.get("model"), str):
                return uni.get("model")
        v = self._get("openai.chat.model", None)
        return v if isinstance(v, str) else None

    @property
    def openai_chat_temperature(self) -> float | None:
        v = self._get("openai.chat.temperature", None)
        return v if v is not None else self.temperature

    @property
    def openai_chat_max_tokens(self) -> int | None:
        v = self._get("openai.chat.max_tokens", None)
        return v if v is not None else self.max_tokens

    @property
    def openai_chat_options(self) -> dict:
        prov = self.get_provider_config("openai")
        opts = prov.get("options") if isinstance(prov, dict) else None
        return opts if isinstance(opts, dict) else {}

    # Generic provider config helpers
    def get_provider_config(self, provider: str) -> dict:
        """Return merged provider config: providers.<name> over openai/<legacy>.

        Backward compatibility: for provider=="openai", merge with `openai` section.
        """
        merged: dict = {}
        if provider == "openai":
            cfg = self._get("openai", None)
            if isinstance(cfg, dict):
                merged.update(cfg)
        prov = self._get(f"providers.{provider}", None)
        if isinstance(prov, dict):
            merged.update(prov)
        return merged

    # Agent profile helpers
    def get_agent_profile(self, name: str | None) -> dict:
        if not name:
            name = "default"
        agents = self._get("agents", {})
        prof = agents.get(name) if isinstance(agents, dict) else None
        return prof if isinstance(prof, dict) else {}

    # Server Configuration
    @property
    def server_host(self) -> str:
        return self._get("server_host", "localhost", "SERVER_HOST")

    @property
    def server_port(self) -> int:
        return self._get("server_port", 8765, "SERVER_PORT")

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
        # Canonical: from models.agents.universal.model, fallback to env/legacy
        agents = self._get("models.agents", None)
        if isinstance(agents, dict):
            uni = agents.get("universal")
            if isinstance(uni, dict) and isinstance(uni.get("model"), str):
                return str(uni.get("model"))
        legacy = self._get("model", "gpt-5", "MODEL")
        return str(legacy)

    @property
    def temperature(self) -> float:
        # Deprecated: kept for back-compat; not part of agents anymore
        v = self._get("temperature", 0.7, "TEMPERATURE")
        return float(v)

    @property
    def reasoning_effort(self) -> str:
        # Deprecated: move to providers.openai.chat.options
        v = self._get("reasoning_effort", "low", "REASONING_EFFORT")
        return str(v)

    @property
    def embedding_model(self) -> str:
        v = self._get("embedding_model", "text-embedding-3-small", "EMBEDDING_MODEL")
        return str(v)

    @property
    def openai_embeddings_model(self) -> str:
        m = self._get("models.embeddings.model", None)
        if isinstance(m, str) and m:
            return m
        return self.embedding_model

    @property
    def max_tokens(self) -> int:
        # Deprecated: kept for back-compat; not part of agents anymore
        v = self._get("max_tokens", 4000, "MAX_TOKENS")
        return int(v)

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
