"""Logging configuration for uvicorn and the application."""

import json
import logging
import os
from datetime import datetime


class UvicornJSONFormatter(logging.Formatter):
    """JSON formatter for uvicorn logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add specific fields for access logs
        if hasattr(record, "scope"):
            scope = record.scope
            log_data["method"] = scope.get("method", "")
            log_data["path"] = scope.get("path", "")
            log_data["client"] = (
                f"{scope.get('client', ['', ''])[0]}:{scope.get('client', ['', ''])[1]}"
            )

        # Add status code if available
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code

        return json.dumps(log_data)


class UvicornPrettyFormatter(logging.Formatter):
    """Pretty formatter for uvicorn logs."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    GRAY = "\033[90m"

    def format(self, record: logging.LogRecord) -> str:
        # Time in gray
        time_str = (
            f"{self.GRAY}{datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]}{self.RESET}"
        )

        # Level with color
        level_color = self.COLORS.get(record.levelname, self.RESET)
        level_str = f"{level_color}{record.levelname:8}{self.RESET}"

        # Logger name - make it shorter and nicer
        logger_name = record.name
        if logger_name == "uvicorn.error":
            logger_name = "server"
        elif logger_name == "uvicorn.access":
            logger_name = "http"

        logger_str = f"{self.GRAY}[{logger_name:10}]{self.RESET}"

        # Message
        msg = record.getMessage()

        return f"{time_str} {level_str} {logger_str} {msg}"


# Choose formatter based on environment variable
formatter_class = (
    UvicornPrettyFormatter
    if os.getenv("LOG_FORMAT", "pretty").lower() == "pretty"
    else UvicornJSONFormatter
)
formatter_name = (
    "pretty" if os.getenv("LOG_FORMAT", "pretty").lower() == "pretty" else "json"
)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        formatter_name: {
            "()": formatter_class,
        },
    },
    "handlers": {
        "default": {
            "formatter": formatter_name,
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
