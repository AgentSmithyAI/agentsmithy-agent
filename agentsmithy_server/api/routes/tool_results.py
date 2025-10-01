"""API routes for tool results access."""

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy_server.api.deps import get_project
from agentsmithy_server.api.schemas import ToolResultResponse
from agentsmithy_server.core.project import Project
from agentsmithy_server.core.tool_results_storage import ToolResultsStorage
from agentsmithy_server.utils.logger import api_logger

router = APIRouter()


@router.get("/api/dialogs/{dialog_id}/tool-results", response_model=list[dict])
async def list_tool_results(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
):
    """List all tool results for a dialog.

    Returns metadata for all stored tool results without loading full content.
    """
    api_logger.info("Listing tool results", dialog_id=dialog_id)

    with ToolResultsStorage(project, dialog_id) as storage:
        results = await storage.list_results()

    return [
        {
            "tool_call_id": r.tool_call_id,
            "tool_name": r.tool_name,
            "timestamp": r.timestamp,
            "size_bytes": r.size_bytes,
            "summary": r.summary,
            "error": r.error,
        }
        for r in results
    ]


@router.get("/api/dialogs/{dialog_id}/tool-results/{tool_call_id}")
async def get_tool_result(
    dialog_id: str,
    tool_call_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> ToolResultResponse:
    """Retrieve full tool execution result.

    Returns the complete tool result including arguments and output.
    """
    api_logger.info(
        "Retrieving tool result",
        dialog_id=dialog_id,
        tool_call_id=tool_call_id,
    )

    with ToolResultsStorage(project, dialog_id) as storage:
        result = await storage.get_result(tool_call_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Tool result not found: {tool_call_id}",
        )

    # Get metadata for additional info
    metadata = await storage.get_metadata(tool_call_id)

    return ToolResultResponse(
        tool_call_id=result["tool_call_id"],
        tool_name=result["tool_name"],
        args=result["args"],
        result=result["result"],
        timestamp=result["timestamp"],
        metadata={
            "size_bytes": metadata.size_bytes if metadata else 0,
            "summary": metadata.summary if metadata else "",
        },
    )
