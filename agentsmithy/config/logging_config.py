"""Logging configuration for uvicorn and the application."""

import logging
import os

import structlog


def get_uvicorn_log_level():
    """Get log level for uvicorn from environment."""
    level = os.getenv("UVICORN_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


def get_log_format():
    """Get log format from environment."""
    return os.getenv("LOG_FORMAT", "pretty").lower()


def get_log_colors():
    """Get log colors setting from environment."""
    colors_env = os.getenv("LOG_COLORS", "true").lower()
    return colors_env in ("true", "1", "yes", "on")


class RenameLoggerProcessor:
    """Processor to rename confusing logger names."""

    def __call__(self, logger, name, event_dict):
        # Rename uvicorn.error to something less confusing
        if event_dict.get("logger") == "uvicorn.error":
            event_dict["logger"] = "uvicorn.server"
        elif event_dict.get("logger") == "uvicorn.access":
            event_dict["logger"] = "uvicorn.http"
        return event_dict


def get_logging_config():
    """Get uvicorn logging configuration based on environment settings."""
    log_format = get_log_format()
    log_colors = get_log_colors()

    # Choose renderer based on format and colors
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=log_colors)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": renderer,
                "foreign_pre_chain": [
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    RenameLoggerProcessor(),  # Rename loggers for clarity
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.UnicodeDecoder(),
                ],
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"],
                "level": get_uvicorn_log_level(),
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": get_uvicorn_log_level(),
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": get_uvicorn_log_level(),
                "propagate": False,
            },
            "httpx": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "openai": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            # Suppress noisy INFO logs from ddgs dependency 'primp'
            "primp": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "primp.primp": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }


# Uvicorn logging configuration (backwards compatibility)
LOGGING_CONFIG = get_logging_config()
