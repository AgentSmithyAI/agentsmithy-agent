from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from agentsmithy.api.deps import get_project
from agentsmithy.api.schemas import HealthResponse
from agentsmithy.core.project import Project
from agentsmithy.core.project_runtime import read_status
from agentsmithy.utils.logger import api_logger

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(project: Project = Depends(get_project)):  # noqa: B008
    """Health check endpoint with server status information.

    Returns status information including:
    - server_status: current server state (starting/ready/stopping/stopped)
    - port: server port
    - pid: server process ID
    """
    try:
        status_doc = read_status(project)
        return HealthResponse(
            status="ok",
            service="agentsmithy-server",
            server_status=status_doc.get("server_status"),
            port=status_doc.get("port"),
            pid=os.getpid(),  # Current process PID
            server_error=status_doc.get("server_error"),
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
        )
