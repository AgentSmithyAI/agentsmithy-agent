"""Configuration module for AgentSmithy server."""

from .defaults import get_default_config
from .logging_config import LOGGING_CONFIG
from .manager import ConfigManager, create_config_manager, get_config_manager
from .providers import (
    ConfigProvider,
    LayeredConfigProvider,
    LocalFileConfigProvider,
    RemoteConfigProvider,
)
from .schema import ConfigValidationError
from .settings import Settings, settings

__all__ = [
    "settings",
    "Settings",
    "LOGGING_CONFIG",
    "ConfigManager",
    "ConfigValidationError",
    "create_config_manager",
    "get_config_manager",
    "ConfigProvider",
    "LayeredConfigProvider",
    "LocalFileConfigProvider",
    "RemoteConfigProvider",
    "get_default_config",
]
