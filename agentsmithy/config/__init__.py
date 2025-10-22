"""Configuration module for AgentSmithy server."""

from .defaults import get_default_config
from .logging_config import LOGGING_CONFIG
from .manager import ConfigManager, create_config_manager, get_config_manager
from .providers import ConfigProvider, LocalFileConfigProvider, RemoteConfigProvider
from .settings import Settings, settings

__all__ = [
    "settings",
    "Settings",
    "LOGGING_CONFIG",
    "ConfigManager",
    "create_config_manager",
    "get_config_manager",
    "ConfigProvider",
    "LocalFileConfigProvider",
    "RemoteConfigProvider",
    "get_default_config",
]
