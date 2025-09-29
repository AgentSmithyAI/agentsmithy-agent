"""Structured logging for AgentSmithy server using structlog."""

import logging
import os

import structlog
from structlog.types import FilteringBoundLogger


# Configure structlog based on environment
def configure_structlog():
    """Configure structlog with pretty or JSON output based on LOG_FORMAT env."""
    log_format = os.getenv("LOG_FORMAT", "pretty").lower()

    # Setup root logger with handler
    logging.root.handlers = []
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)

    # Common processors
    processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on format
    if log_format == "json":
        processors.extend(
            [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
        )
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Configure structlog on module import
configure_structlog()


# Helper functions for special log types
def request_log(
    logger: FilteringBoundLogger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **kwargs,
):
    """Log HTTP request with details."""
    logger.info(
        f"{method} {path} - {status_code}",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs,
    )


def stream_log(
    logger: FilteringBoundLogger, event_type: str, content: str | None = None, **kwargs
):
    """Log SSE streaming events."""
    logger.debug(
        f"SSE Event: {event_type}",
        event_type=event_type,
        content=content[:300] if content else None,  # Truncate long content
        **kwargs,
    )


# Create loggers directly with structlog
def get_logger(name: str, level: int = logging.INFO) -> FilteringBoundLogger:
    """Get a configured structlog logger."""
    stdlib_logger = logging.getLogger(name)
    stdlib_logger.setLevel(level)
    return structlog.get_logger(name)


# Global logger instances
logger = get_logger("agentsmithy")
api_logger = get_logger("agentsmithy.api", level=logging.DEBUG)
agent_logger = get_logger("agentsmithy.agents", level=logging.DEBUG)
rag_logger = get_logger("agentsmithy.rag", level=logging.DEBUG)
