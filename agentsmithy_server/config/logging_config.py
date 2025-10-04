"""Logging configuration for uvicorn and the application."""

import logging
import os

import structlog


def get_uvicorn_log_level():
    """Get log level for uvicorn from environment."""
    level = os.getenv("UVICORN_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


class RenameLoggerProcessor:
    """Processor to rename confusing logger names."""

    def __call__(self, logger, name, event_dict):
        # Rename uvicorn.error to something less confusing
        if event_dict.get("logger") == "uvicorn.error":
            event_dict["logger"] = "uvicorn.server"
        elif event_dict.get("logger") == "uvicorn.access":
            event_dict["logger"] = "uvicorn.http"
        return event_dict


# Uvicorn logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(colors=True),
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
            "level": "WARNING",
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
