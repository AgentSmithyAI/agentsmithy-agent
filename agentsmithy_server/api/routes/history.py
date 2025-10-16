"""History endpoint: retrieve complete dialog history with reasoning and tool calls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy_server.api.deps import get_project
from agentsmithy_server.api.schemas import (
    DialogHistoryResponse,
    HistoryEvent,
)
from agentsmithy_server.core.dialog_reasoning_storage import DialogReasoningStorage
from agentsmithy_server.core.project import Project
from agentsmithy_server.utils.logger import api_logger

router = APIRouter()


async def _build_history_response(
    project: Project, dialog_id: str
) -> DialogHistoryResponse:
    """Build complete history response as SSE event stream."""
    # Get messages from history and convert to SSE events
    base_events: list[tuple[int, HistoryEvent]] = []
    try:
        history = project.get_dialog_history(dialog_id)
        messages = history.get_messages()

        for idx, msg in enumerate(messages):
            msg_type = msg.type

            # Skip ToolMessage - those are results, not events
            if msg_type == "tool":
                continue

            # Convert LangChain types to SSE types
            if msg_type == "human":
                event_type = "user"
            elif msg_type == "ai":
                event_type = "chat"
            else:
                # system, etc - keep as is
                event_type = msg_type

            # Add message as chat/user event
            base_events.append(
                (
                    idx,
                    HistoryEvent(
                        type=event_type,
                        content=(
                            msg.content
                            if isinstance(msg.content, str)
                            else str(msg.content)
                        ),
                    ),
                )
            )

            # Extract tool_calls and add as separate tool_call events
            try:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tc_id = (
                            tc.get("id")
                            if isinstance(tc, dict)
                            else getattr(tc, "id", "")
                        )
                        tc_name = (
                            tc.get("name")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", "")
                        )
                        tc_args = (
                            tc.get("args")
                            if isinstance(tc, dict)
                            else getattr(tc, "args", {})
                        )
                        base_events.append(
                            (
                                idx,  # Same position as AI message
                                HistoryEvent(
                                    type="tool_call",
                                    id=tc_id,
                                    name=tc_name,
                                    args=tc_args,
                                ),
                            )
                        )
            except Exception:
                pass
    except Exception as e:
        api_logger.error(
            "Failed to load messages", exc_info=True, error=str(e), dialog_id=dialog_id
        )

    # Get reasoning blocks and merge into events
    reasoning_count = 0
    reasoning_events: list[tuple[int, HistoryEvent]] = []
    try:
        with DialogReasoningStorage(project, dialog_id) as storage:
            blocks = storage.get_all()
            for block in blocks:
                # Create reasoning event to insert before related message
                reasoning_events.append(
                    (
                        block.message_index,  # Sort key - insert before this message
                        HistoryEvent(
                            type="reasoning",
                            content=block.content,
                            model_name=block.model_name,
                        ),
                    )
                )
                reasoning_count += 1
    except Exception as e:
        api_logger.error(
            "Failed to load reasoning",
            exc_info=True,
            error=str(e),
            dialog_id=dialog_id,
        )

    # Merge all events and sort
    # For same index: reasoning (type=0) comes before other events (type=1)
    all_events = base_events + reasoning_events
    all_events.sort(key=lambda x: (x[0], 0 if x[1].type == "reasoning" else 1))

    # Extract events in sorted order
    events_data: list[HistoryEvent] = [evt for _, evt in all_events]

    return DialogHistoryResponse(
        dialog_id=dialog_id,
        events=events_data,
    )


@router.get("/api/dialogs/{dialog_id}/history", response_model_exclude_none=True)
async def get_dialog_history(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> DialogHistoryResponse:
    """Get complete history for a dialog as SSE event stream.

    Args:
        dialog_id: Dialog identifier

    Returns:
        Dialog history as SSE events (same format as streaming)

    Example response:
        {
            "dialog_id": "01J...",
            "events": [
                {"type": "user", "content": "read file.txt"},
                {"type": "reasoning", "content": "I need to read..."},
                {"type": "chat", "content": "I'll read the file..."},
                {"type": "tool_call", "name": "read_file", "args": {"path": "file.txt"}},
                {"type": "chat", "content": "File contains..."}
            ]
        }
    """
    api_logger.info("Fetching dialog history", dialog_id=dialog_id)

    # Check if dialog exists
    try:
        dialogs = project.list_dialogs()
        if not any(d["id"] == dialog_id for d in dialogs):
            raise HTTPException(status_code=404, detail=f"Dialog {dialog_id} not found")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        api_logger.error("Failed to check dialog", exc_info=True, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        response = await _build_history_response(project, dialog_id)
        api_logger.info(
            "Dialog history retrieved",
            dialog_id=dialog_id,
            total_events=len(response.events),
        )
        return response
    except Exception as e:
        api_logger.error(
            "Failed to build history response", exc_info=True, error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
