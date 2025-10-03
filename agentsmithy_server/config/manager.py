"""Configuration manager with hot-reload support."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from agentsmithy_server.config.providers import ConfigProvider, LocalFileConfigProvider
from agentsmithy_server.utils.logger import get_logger

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
        self._config[key] = value
        await self.provider.save(self._config)
        logger.info("Configuration updated", key=key)
        self._notify_callbacks()

    async def update(self, updates: dict[str, Any]) -> None:
        """Update multiple configuration values at once."""
        self._config.update(updates)
        await self.provider.save(self._config)
        logger.info("Configuration updated", keys=list(updates.keys()))
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
    config_dir: Path,
    defaults: dict[str, Any] | None = None,
) -> ConfigManager:
    """Create and initialize the global config manager.

    Args:
        config_dir: Directory to store config.json
        defaults: Default configuration values
    """
    global _config_manager

    config_path = config_dir / "config.json"
    provider = LocalFileConfigProvider(config_path, defaults=defaults)
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
