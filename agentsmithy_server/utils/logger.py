"""Structured logging for AgentSmithy server."""

import json
import logging
import os
import traceback
from datetime import datetime
from typing import Optional


class PrettyFormatter(logging.Formatter):
    """Pretty formatter for development with colors."""

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
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        # Time in gray
        time_str = (
            f"{self.GRAY}{datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]}{self.RESET}"
        )

        # Level with color
        level_color = self.COLORS.get(record.levelname, self.RESET)
        level_str = f"{level_color}{record.levelname:8}{self.RESET}"

        # Logger name in gray
        logger_str = f"{self.GRAY}[{record.name:20}]{self.RESET}"

        # Message
        msg = record.getMessage()

        # Add extra fields if present
        extras = []
        if hasattr(record, "extra_fields") and record.extra_fields:
            for key, value in record.extra_fields.items():
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                extras.append(f"{self.GRAY}{key}={self.RESET}{value}")

        # Build final message
        parts = [time_str, level_str, logger_str, msg]
        if extras:
            parts.append(
                f"{self.GRAY}|{self.RESET} "
                + f" {self.GRAY}|{self.RESET} ".join(extras)
            )

        result = " ".join(parts)

        # Add exception info if present
        if record.exc_info:
            result += f"\n{self.COLORS['ERROR']}{''.join(traceback.format_exception(*record.exc_info))}{self.RESET}"

        return result


class StructuredLogger:
    """Structured logger with JSON output for better debugging."""

    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Disable propagation to prevent duplicate logs
        self.logger.propagate = False

        # Remove existing handlers
        self.logger.handlers = []

        # Create console handler with custom formatter
        handler = logging.StreamHandler()

        # Use pretty formatter by default, JSON only if specified
        log_format = os.getenv("LOG_FORMAT", "pretty").lower()
        if log_format == "json":
            handler.setFormatter(self.StructuredFormatter())
        else:
            handler.setFormatter(PrettyFormatter())

        self.logger.addHandler(handler)

    class StructuredFormatter(logging.Formatter):
        """Custom formatter that outputs structured JSON logs."""

        def format(self, record: logging.LogRecord) -> str:
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            # Add extra fields if present
            if hasattr(record, "extra_fields"):
                log_data.update(record.extra_fields)

            # Add exception info if present
            if record.exc_info:
                log_data["exception"] = {
                    "type": record.exc_info[0].__name__,
                    "message": str(record.exc_info[1]),
                    "traceback": traceback.format_exception(*record.exc_info),
                }

            return json.dumps(log_data)

    def _log(self, level: int, message: str, **kwargs):
        """Internal log method with extra fields."""
        extra = {"extra_fields": kwargs} if kwargs else {}
        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message with optional extra fields."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message with optional extra fields."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with optional extra fields."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message with optional exception and extra fields."""
        if exception:
            kwargs["error_type"] = type(exception).__name__
            kwargs["error_message"] = str(exception)
            self.logger.error(
                message, exc_info=exception, extra={"extra_fields": kwargs}
            )
        else:
            self._log(logging.ERROR, message, **kwargs)

    def request_log(
        self, method: str, path: str, status_code: int, duration_ms: float, **kwargs
    ):
        """Log HTTP request with details."""
        self.info(
            f"{method} {path} - {status_code}",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs,
        )

    def stream_log(self, event_type: str, content: Optional[str] = None, **kwargs):
        """Log SSE streaming events."""
        self.debug(
            f"SSE Event: {event_type}",
            event_type=event_type,
            content=content[:100] if content else None,  # Truncate long content
            **kwargs,
        )


# Global logger instance
logger = StructuredLogger("agentsmithy")

# Create specialized loggers with DEBUG level for better diagnostics
api_logger = StructuredLogger("agentsmithy.api", level=logging.DEBUG)
agent_logger = StructuredLogger("agentsmithy.agents", level=logging.DEBUG)
rag_logger = StructuredLogger("agentsmithy.rag", level=logging.DEBUG)
