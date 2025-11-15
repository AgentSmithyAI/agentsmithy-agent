from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from agentsmithy.api.deps import get_project
from agentsmithy.api.schemas import HealthResponse
from agentsmithy.config import settings
from agentsmithy.core.project import Project
from agentsmithy.core.project_runtime import read_status
from agentsmithy.utils.logger import api_logger

router = APIRouter()


def check_config_validity() -> tuple[bool, list[str]]:
    """Check if configuration is valid and return errors if any."""
    errors = []
    try:
        settings.validate_or_raise()
        return True, []
    except ValueError as e:
        error_msg = str(e)
        if "OPENAI_API_KEY" in error_msg or "api_key" in error_msg.lower():
            errors.append("API key not configured")
        if "model" in error_msg.lower():
            errors.append("Model not configured or unsupported")
        if "embedding" in error_msg.lower():
            errors.append("Embedding model not configured or unsupported")
        if not errors:
            errors.append(error_msg)
        return False, errors


@router.get("/health", response_model=HealthResponse)
async def health(project: Project | None = Depends(get_project)):  # noqa: B008
    """Health check endpoint with server status information.

    Returns status information including:
    - server_status: current server state (starting/ready/stopping/stopped)
    - port: server port
    - pid: server process ID
    - config_valid: whether configuration is complete (API keys set, etc)
    - config_errors: list of configuration issues if any
    """
    try:
        status_doc = {}
        if project:
            status_doc = read_status(project)

        # Check configuration validity
        config_valid, config_errors = check_config_validity()

        return HealthResponse(
            status="ok",
            service="agentsmithy-server",
            server_status=status_doc.get("server_status"),
            port=status_doc.get("port"),
            pid=os.getpid(),  # Current process PID
            server_error=status_doc.get("server_error"),
            config_valid=config_valid,
            config_errors=config_errors if config_errors else None,
        )
    except Exception as e:
        # Log the error - this might indicate permissions issues, corrupt file, etc.
        api_logger.error(
            "Failed to read server status file",
            error=str(e),
            exc_info=True,
        )
        return HealthResponse(
            status="ok",
            service="agentsmithy-server",
            server_status="unknown",
            server_error=f"Failed to read status: {str(e)}",
            config_valid=None,
            config_errors=None,
        )
