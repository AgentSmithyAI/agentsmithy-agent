"""Configuration providers - abstract and concrete implementations."""

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agentsmithy.config.schema import deep_merge, normalize_config
from agentsmithy.utils.logger import get_logger

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

    def __init__(
        self,
        config_path: Path,
        defaults: dict[str, Any] | None = None,
        *,
        create_if_missing: bool = True,
    ):
        self.config_path = config_path
        self.defaults = defaults or {}
        self._observer: Any = None  # Observer from watchdog
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._last_mtime: float | None = None
        self._last_valid_config: dict[str, Any] | None = None
        self._user_config: dict[str, Any] | None = (
            None  # Original user config without defaults
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self.create_if_missing = create_if_missing

    async def load(self) -> dict[str, Any]:
        """Load configuration from file, creating with defaults if not exists."""
        if not self.config_path.exists():
            if not self.create_if_missing:
                logger.info(
                    "Config file not found, skipping auto-create",
                    path=str(self.config_path),
                )
                merged = self.defaults.copy()
                self._last_valid_config = merged.copy()
                self._user_config = {}
                return merged
            logger.info(
                "Config file not found, creating with defaults",
                path=str(self.config_path),
            )
            await self.save(self.defaults.copy())
            self._last_valid_config = self.defaults.copy()
            self._user_config = self.defaults.copy()
            return self.defaults.copy()

        try:
            content = self.config_path.read_text(encoding="utf-8")
            config = json.loads(content)
            self._last_mtime = self.config_path.stat().st_mtime

            merged = deep_merge(self.defaults, config)
            normalized = normalize_config(merged)

            if normalized != merged:
                logger.info(
                    "Loaded legacy config; applying normalized view in memory only",
                    path=str(self.config_path),
                )

            self._last_valid_config = normalized.copy()
            self._user_config = config.copy()

            logger.debug("Config loaded from file", path=str(self.config_path))
            return normalized
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
        except ValueError as exc:
            logger.error(
                "Invalid configuration structure",
                error=str(exc),
                path=str(self.config_path),
            )
            raise
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
            merged = normalize_config(deep_merge(self.defaults, config))
        except ValueError as exc:
            logger.error(
                "Refusing to save invalid configuration",
                error=str(exc),
                path=str(self.config_path),
            )
            raise

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.config_path.with_suffix(".tmp")
            content = json.dumps(merged, ensure_ascii=False, indent=2)
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(self.config_path)

            self._last_mtime = self.config_path.stat().st_mtime
            self._user_config = merged.copy()
            self._last_valid_config = merged.copy()
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

            def _handle_event(self, event):
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
                    if not self.provider.create_if_missing:
                        # File might not exist yet; allow load() to handle
                        pass
                    else:
                        return

                logger.debug("Config file changed, reloading", path=event.src_path)

                # Schedule coroutine in the main event loop from this thread
                if self.provider._loop and not self.provider._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self.provider._handle_file_change(), self.provider._loop
                    )

            def on_modified(self, event):
                self._handle_event(event)

            def on_created(self, event):
                self._handle_event(event)

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
            try:
                # Run blocking operations in executor to avoid blocking event loop
                # Use asyncio.wait_for to add timeout protection
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._observer.stop), timeout=2.0
                )
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None, lambda: self._observer.join(timeout=1.0)
                    ),
                    timeout=2.0,
                )
                logger.info("Stopped watching config file")
            except (TimeoutError, asyncio.CancelledError) as e:
                # Graceful handling during shutdown
                logger.debug(f"Observer stop interrupted: {type(e).__name__}")
                # Force stop observer in case it's stuck
                try:
                    self._observer.stop()
                except Exception:
                    pass
            finally:
                self._observer = None


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


class LayeredConfigProvider(ConfigProvider):
    """Configuration provider that merges multiple config sources.

    Each layer is a ConfigProvider implementation ordered from lowest to highest
    precedence. By default, writes go to the first provider (typically the
    global/user-level config). Additional providers can represent per-project
    overrides, remote configs, etc.
    """

    def __init__(
        self,
        providers: list[ConfigProvider],
        *,
        primary_index: int = 0,
    ):
        if not providers:
            raise ValueError("LayeredConfigProvider requires at least one provider")
        if primary_index < 0 or primary_index >= len(providers):
            raise ValueError("primary_index must point to an existing provider layer")

        self.providers = providers
        self.primary_index = primary_index
        self._layer_configs: list[dict[str, Any]] = [{} for _ in providers]
        self._callback: Callable[[dict[str, Any]], None] | None = None

    def _merge(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for cfg in self._layer_configs:
            merged.update(cfg)
        return merged

    def _emit(self) -> None:
        if self._callback:
            self._callback(self._merge())

    async def load(self) -> dict[str, Any]:
        for idx, provider in enumerate(self.providers):
            cfg = await provider.load()
            self._layer_configs[idx] = cfg
        return self._merge()

    async def save(self, config: dict[str, Any]) -> None:
        """Persist updates via the primary (writable) provider."""
        primary = self.providers[self.primary_index]
        await primary.save(config)
        # Refresh primary cache and emit merged view
        self._layer_configs[self.primary_index] = await primary.load()
        self._emit()

    async def watch(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._callback = callback

        async def _attach(idx: int, provider: ConfigProvider) -> None:
            def handle_change(new_config: dict[str, Any]) -> None:
                self._layer_configs[idx] = new_config
                self._emit()

            await provider.watch(handle_change)

        for idx, provider in enumerate(self.providers):
            await _attach(idx, provider)

    async def stop_watching(self) -> None:
        for provider in self.providers:
            await provider.stop_watching()
