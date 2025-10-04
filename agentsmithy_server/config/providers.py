"""Configuration providers - abstract and concrete implementations."""

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agentsmithy_server.utils.logger import get_logger

logger = get_logger("config.providers")


class ConfigProvider(ABC):
    """Abstract base class for configuration providers."""

    @abstractmethod
    async def load(self) -> dict[str, Any]:
        """Load configuration from the provider."""
        pass

    @abstractmethod
    async def save(self, config: dict[str, Any]) -> None:
        """Save configuration to the provider."""
        pass

    @abstractmethod
    async def watch(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Watch for configuration changes and call callback when changed."""
        pass

    @abstractmethod
    async def stop_watching(self) -> None:
        """Stop watching for configuration changes."""
        pass


class LocalFileConfigProvider(ConfigProvider):
    """Configuration provider that stores config in a local JSON file."""

    def __init__(self, config_path: Path, defaults: dict[str, Any] | None = None):
        self.config_path = config_path
        self.defaults = defaults or {}
        self._observer: Any = None  # Observer from watchdog
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._last_mtime: float | None = None
        self._last_valid_config: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def load(self) -> dict[str, Any]:
        """Load configuration from file, creating with defaults if not exists.

        The configuration is deep-merged with defaults in memory:
        - User values take precedence
        - Missing keys are filled from defaults
        - Nested dictionaries are merged recursively
        """
        if not self.config_path.exists():
            logger.info(
                "Config file not found, creating with defaults",
                path=str(self.config_path),
            )
            # Create config file with full defaults on first run
            await self.save(self.defaults.copy())
            self._last_valid_config = self.defaults.copy()
            return self.defaults.copy()

        try:
            content = self.config_path.read_text(encoding="utf-8")
            config = json.loads(content)
            self._last_mtime = self.config_path.stat().st_mtime

            # Deep merge with defaults to ensure all keys exist
            # User config takes precedence, but missing keys are filled from defaults
            merged = self._deep_merge(self.defaults, config)

            # Store as last valid config
            self._last_valid_config = merged

            logger.debug("Config loaded from file", path=str(self.config_path))
            return merged
        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON syntax in config file",
                error=str(e),
                line=e.lineno,
                column=e.colno,
                path=str(self.config_path),
            )
            # Return last valid config if available, otherwise defaults
            if self._last_valid_config is not None:
                logger.warning(
                    "Using last valid configuration due to JSON error",
                    path=str(self.config_path),
                )
                return self._last_valid_config.copy()
            else:
                logger.warning(
                    "No previous valid config, using defaults",
                    path=str(self.config_path),
                )
                return self.defaults.copy()
        except Exception as e:
            logger.error(
                "Failed to load config",
                error=str(e),
                path=str(self.config_path),
            )
            # Return last valid config if available, otherwise defaults
            if self._last_valid_config is not None:
                logger.warning(
                    "Using last valid configuration due to error",
                    path=str(self.config_path),
                )
                return self._last_valid_config.copy()
            else:
                logger.warning(
                    "No previous valid config, using defaults",
                    path=str(self.config_path),
                )
                return self.defaults.copy()

    async def save(self, config: dict[str, Any]) -> None:
        """Atomically save configuration to file."""
        try:
            # Validate JSON before saving
            json.dumps(config)  # This will raise if config is not serializable

            # Ensure parent directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write using temp file
            tmp_path = self.config_path.with_suffix(".tmp")
            content = json.dumps(config, ensure_ascii=False, indent=2)
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(self.config_path)

            self._last_mtime = self.config_path.stat().st_mtime
            self._last_valid_config = config.copy()
            logger.debug("Config saved to file", path=str(self.config_path))
        except Exception as e:
            logger.error(
                "Failed to save config",
                error=str(e),
                path=str(self.config_path),
            )
            raise

    async def watch(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Watch for file changes and reload configuration."""
        self._callback = callback
        # Store reference to the event loop for thread-safe task creation
        self._loop = asyncio.get_running_loop()

        class ConfigFileHandler(FileSystemEventHandler):
            def __init__(self, provider: LocalFileConfigProvider):
                self.provider = provider

            def on_modified(self, event):
                if event.is_directory:
                    return

                # Check if it's our config file
                if (
                    Path(event.src_path).resolve()
                    != self.provider.config_path.resolve()
                ):
                    return

                # Check if file actually changed (avoid duplicate events)
                try:
                    current_mtime = self.provider.config_path.stat().st_mtime
                    if self.provider._last_mtime == current_mtime:
                        return
                except FileNotFoundError:
                    return

                logger.debug("Config file modified, reloading", path=event.src_path)

                # Schedule coroutine in the main event loop from this thread
                if self.provider._loop and not self.provider._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self.provider._handle_file_change(), self.provider._loop
                    )

        self._observer = Observer()
        event_handler = ConfigFileHandler(self)

        # Watch the parent directory (watching file directly doesn't work on all systems)
        watch_dir = self.config_path.parent
        self._observer.schedule(event_handler, str(watch_dir), recursive=False)
        self._observer.start()

        logger.info("Started watching config file", path=str(self.config_path))

    async def _handle_file_change(self) -> None:
        """Internal handler for file changes."""
        try:
            new_config = await self.load()
            if self._callback:
                self._callback(new_config)
        except Exception as e:
            logger.error("Error handling config file change", error=str(e))

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=1.0)
            self._observer = None
            logger.info("Stopped watching config file")

    def _deep_merge(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep merge two dictionaries recursively.

        Values from override take precedence. Nested dicts are merged recursively.
        Lists and other types from override completely replace base values.

        Args:
            base: Base dictionary (defaults)
            override: Override dictionary (user config)

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override value (including lists, primitives, etc.)
                result[key] = value

        return result


class RemoteConfigProvider(ConfigProvider):
    """Placeholder for future remote configuration provider.

    This could fetch config from:
    - HTTP endpoint
    - Git repository
    - Cloud storage (S3, etc.)
    - Configuration service (Consul, etcd, etc.)
    """

    def __init__(self, remote_url: str, cache_path: Path | None = None):
        self.remote_url = remote_url
        self.cache_path = cache_path
        raise NotImplementedError("RemoteConfigProvider not yet implemented")

    async def load(self) -> dict[str, Any]:
        # Fetch from remote, use cache if unavailable
        raise NotImplementedError("RemoteConfigProvider not yet implemented")

    async def save(self, config: dict[str, Any]) -> None:
        # Push to remote if allowed
        raise NotImplementedError("RemoteConfigProvider not yet implemented")

    async def watch(self, callback: Callable[[dict[str, Any]], None]) -> None:
        # Poll remote or use webhooks
        raise NotImplementedError("RemoteConfigProvider not yet implemented")

    async def stop_watching(self) -> None:
        raise NotImplementedError("RemoteConfigProvider not yet implemented")
