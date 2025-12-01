"""Configuration settings for AgentSmithy server.

This module provides a Settings class that wraps the ConfigManager,
providing property-based access to configuration values with hot-reload support.
"""

from __future__ import annotations

import os
from typing import Any

from agentsmithy.config.constants import (
    DEFAULT_CHROMA_PERSIST_DIRECTORY,
    DEFAULT_MAX_CONTEXT_LENGTH,
    DEFAULT_MAX_OPEN_FILES,
    DEFAULT_STREAMING_ENABLED,
)
from agentsmithy.config.manager import ConfigManager


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
        from agentsmithy.config.validation import validate_or_raise as _v

        _v(self.model, self.embedding_model, self.openai_api_key)

    def validation_status(self) -> tuple[bool, list[str]]:
        """Return (is_valid, errors) without raising."""
        try:
            self.validate_or_raise()
            return True, []
        except ValueError as exc:
            return False, self._format_validation_errors(str(exc))

    @staticmethod
    def _format_validation_errors(message: str) -> list[str]:
        """Convert validation error message into structured list."""
        errors: list[str] = []
        lower_msg = message.lower()

        if "api key" in lower_msg or "api_key" in lower_msg:
            errors.append("API key not configured")

        if "embedding" in lower_msg:
            errors.append("Embedding model not configured or unsupported")

        if "model" in lower_msg and "embedding" not in lower_msg:
            errors.append("Model not configured or unsupported")

        # Always include the original validation message for diagnostics,
        # unless it's a verbatim match of a friendly message we already added.
        if message:
            normalized_existing = {err.lower() for err in errors}
            if message.lower() not in normalized_existing:
                errors.append(message)

        return errors

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
        return self.model

    @property
    def openai_chat_options(self) -> dict:
        prov = self.get_provider_config("openai")
        opts = prov.get("options") if isinstance(prov, dict) else None
        return opts if isinstance(opts, dict) else {}

    # Generic provider config helpers
    def get_provider_config(self, provider: str) -> dict:
        """Return provider config from providers.<name>."""
        prov = self._get(f"providers.{provider}", None)
        if isinstance(prov, dict):
            return prov
        return {}

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
        return DEFAULT_CHROMA_PERSIST_DIRECTORY

    @property
    def max_context_length(self) -> int:
        return DEFAULT_MAX_CONTEXT_LENGTH

    @property
    def max_open_files(self) -> int:
        return DEFAULT_MAX_OPEN_FILES

    # Summarization
    @property
    def summary_trigger_token_budget(self) -> int:
        return self._get(
            "summary_trigger_token_budget", 20000, "SUMMARY_TRIGGER_TOKEN_BUDGET"
        )

    # LLM Configuration
    def _get_workload_config(self, workload_name: str) -> dict | None:
        """Get workload config by name.

        Uses direct dict lookup instead of dot-notation because workload names
        can contain dots (e.g., 'gpt-5.1-codex').
        """
        if self._config_manager:
            cfg = self._config_manager.get_all()
            workloads = cfg.get("workloads") if isinstance(cfg, dict) else None
        else:
            workloads = None
        if not isinstance(workloads, dict):
            return None
        wl_config = workloads.get(workload_name)
        return wl_config if isinstance(wl_config, dict) else None

    @property
    def model(self) -> str | None:
        # Resolve from models.agents.universal -> workload -> model
        agents = self._get("models.agents", None)
        if not isinstance(agents, dict):
            return None
        uni = agents.get("universal")
        if not isinstance(uni, dict):
            return None
        workload = uni.get("workload")
        if not workload:
            return None
        wl_config = self._get_workload_config(workload)
        if not wl_config:
            return None
        return wl_config.get("model")

    @property
    def embedding_model(self) -> str | None:
        # Resolve from models.embeddings -> workload -> model
        models = self._get("models.embeddings", None)
        if not isinstance(models, dict):
            return None
        workload = models.get("workload")
        if not workload:
            return None
        wl_config = self._get_workload_config(workload)
        if not wl_config:
            return None
        return wl_config.get("model")

    @property
    def openai_embeddings_model(self) -> str | None:
        return self.embedding_model

    @property
    def streaming_enabled(self) -> bool:
        return DEFAULT_STREAMING_ENABLED

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

    @property
    def log_colors(self) -> bool:
        return self._get("log_colors", True, "LOG_COLORS")


# Global settings instance (will be initialized with config manager)
settings = Settings()
