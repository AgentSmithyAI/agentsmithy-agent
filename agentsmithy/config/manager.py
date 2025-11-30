"""Configuration manager with hot-reload support."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from agentsmithy.config.providers import (
    ConfigProvider,
    LayeredConfigProvider,
    LocalFileConfigProvider,
)
from agentsmithy.config.schema import apply_deletions, deep_merge
from agentsmithy.utils.logger import get_logger

logger = get_logger("config.manager")

T = TypeVar("T")


class ConfigManager:
    """Manages application configuration with hot-reload support.

    Supports multiple providers (local file, remote, etc.) and allows
    registering callbacks for configuration changes.
    """

    def __init__(self, provider: ConfigProvider):
        self.provider = provider
        self._config: dict[str, Any] = {}
        self._change_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._loaded = False

    async def initialize(self) -> None:
        """Initialize the config manager by loading initial config and starting watch."""
        self._config = await self.provider.load()
        self._loaded = True
        logger.info("Configuration initialized", config_keys=list(self._config.keys()))

    async def start_watching(self) -> None:
        """Start watching for configuration changes."""
        await self.provider.watch(self._on_config_changed)

    async def stop_watching(self) -> None:
        """Stop watching for configuration changes."""
        await self.provider.stop_watching()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return self._config.get(key, default)

    def get_typed(self, key: str, expected_type: type[T], default: T) -> T:
        """Get a typed configuration value with validation."""
        value = self._config.get(key, default)
        if not isinstance(value, expected_type):
            logger.warning(
                "Config type mismatch, using default",
                key=key,
                expected=expected_type.__name__,
                actual=type(value).__name__,
            )
            return default
        return value

    def get_str(self, key: str, default: str = "") -> str:
        """Get a string configuration value."""
        return self.get_typed(key, str, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer configuration value."""
        return self.get_typed(key, int, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a float configuration value."""
        return self.get_typed(key, float, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        return self.get_typed(key, bool, default)

    async def set(self, key: str, value: Any) -> None:
        """Set a configuration value and persist it."""
        # Update in-memory config
        self._config[key] = value

        # Update only user config (without defaults)
        if (
            hasattr(self.provider, "_user_config")
            and self.provider._user_config is not None
        ):
            self.provider._user_config[key] = value
            await self.provider.save(self.provider._user_config)
        else:
            # Fallback for providers without user_config tracking
            await self.provider.save(self._config)

        logger.info("Configuration updated", key=key)
        self._notify_callbacks()

    async def update(self, updates: dict[str, Any]) -> None:
        """Update multiple configuration values at once."""
        # Update in-memory config with deep merge
        self._config = deep_merge(self._config, updates)

        # Update only user config (without defaults)
        if (
            hasattr(self.provider, "_user_config")
            and self.provider._user_config is not None
        ):
            user_cfg = self.provider._user_config
            if not isinstance(user_cfg, dict):
                user_cfg = {}
            user_cfg = deep_merge(user_cfg, updates)
            self.provider._user_config = user_cfg
            await self.provider.save(user_cfg)
        else:
            # Fallback for providers without user_config tracking
            await self.provider.save(self._config)

        logger.info("Configuration updated", keys=list(updates.keys()))
        self._notify_callbacks()

    async def update_with_deletions(self, updates: dict[str, Any]) -> None:
        """Update config values, treating null values as deletions.

        Unlike update(), this method will remove keys where updates has null values.
        Used by API to handle requests like {"providers": {"old-provider": null}}.
        """
        # First merge, then apply deletions
        self._config = deep_merge(self._config, updates)
        self._config = apply_deletions(self._config, updates)

        # Update only user config (without defaults)
        if (
            hasattr(self.provider, "_user_config")
            and self.provider._user_config is not None
        ):
            user_cfg = self.provider._user_config
            if not isinstance(user_cfg, dict):
                user_cfg = {}
            user_cfg = deep_merge(user_cfg, updates)
            user_cfg = apply_deletions(user_cfg, updates)
            self.provider._user_config = user_cfg
            await self.provider.save(user_cfg)
        else:
            # Fallback for providers without user_config tracking
            await self.provider.save(self._config)

        logger.info("Configuration updated with deletions", keys=list(updates.keys()))
        self._notify_callbacks()

    def get_all(self) -> dict[str, Any]:
        """Get the entire configuration dictionary."""
        return self._config.copy()

    def register_change_callback(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback to be called when configuration changes."""
        self._change_callbacks.append(callback)

    def _on_config_changed(self, new_config: dict[str, Any]) -> None:
        """Internal handler for configuration changes from provider."""
        old_config = self._config.copy()
        self._config = new_config

        # Log what changed
        changed_keys = []
        for key in set(old_config.keys()) | set(new_config.keys()):
            if old_config.get(key) != new_config.get(key):
                changed_keys.append(key)

        if changed_keys:
            logger.info("Configuration reloaded", changed_keys=changed_keys)
        else:
            logger.debug("Configuration reloaded with no changes")

        self._notify_callbacks()

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of configuration change."""
        for callback in self._change_callbacks:
            try:
                callback(self._config.copy())
            except Exception as e:
                logger.error(
                    "Error in config change callback",
                    error=str(e),
                    callback=callback.__name__,
                )


# Global config manager instance
_config_manager: ConfigManager | None = None


def create_config_manager(
    global_config_dir: Path,
    *,
    local_config_path: Path | None = None,
    defaults: dict[str, Any] | None = None,
) -> ConfigManager:
    """Create and initialize the global config manager.

    Args:
        global_config_dir: Directory to store global config.json
        local_config_path: Optional project-scoped config.json for overrides
        defaults: Default configuration values
    """
    global _config_manager

    config_path = global_config_dir / "config.json"
    base_provider = LocalFileConfigProvider(config_path, defaults=defaults)
    providers: list[ConfigProvider] = [base_provider]
    if local_config_path:
        providers.append(
            LocalFileConfigProvider(
                local_config_path, defaults={}, create_if_missing=False
            )
        )

    if len(providers) == 1:
        provider: ConfigProvider = base_provider
    else:
        provider = LayeredConfigProvider(providers, primary_index=0)
    _config_manager = ConfigManager(provider)

    logger.info("Config manager created", config_path=str(config_path))
    return _config_manager


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance."""
    if _config_manager is None:
        raise RuntimeError(
            "Config manager not initialized. Call create_config_manager() first."
        )
    return _config_manager
