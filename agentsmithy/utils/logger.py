"""Structured logging for AgentSmithy server using structlog."""

import logging
import os

import structlog
from structlog.types import FilteringBoundLogger


# Configure structlog based on environment
def configure_structlog():
    """Configure structlog with pretty or JSON output based on LOG_FORMAT env.

    Properly route stdlib logging through structlog so external libs are structured
    and controllable by levels. No stdout/stderr suppression hacks needed.
    """
    log_format = os.getenv("LOG_FORMAT", "pretty").lower()
    log_colors_env = os.getenv("LOG_COLORS", "true").lower()
    log_colors = log_colors_env in ("true", "1", "yes", "on")

    # Choose renderer for final output
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=log_colors)

    # Root logger + handler with ProcessorFormatter
    logging.root.handlers = []
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
        )
    )
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)

    # Capture warnings to logging
    logging.captureWarnings(True)

    # Library log levels (inherited fmt via ProcessorFormatter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)
    logging.getLogger("ddgs").setLevel(logging.WARNING)
    logging.getLogger("duckduckgo_search").setLevel(logging.WARNING)
    # Verbose HTTP response logs come from primp used by ddgs
    logging.getLogger("primp").setLevel(logging.WARNING)
    logging.getLogger("primp.primp").setLevel(logging.WARNING)

    # structlog pipeline; wrap_for_formatter hands off to ProcessorFormatter above
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            # format_exc_info removed - conflicts with pretty exception rendering when exc_info=True
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
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
