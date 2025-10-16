"""History endpoint: retrieve complete dialog history with reasoning and tool calls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy_server.api.deps import get_project
from agentsmithy_server.api.schemas import (
    DialogHistoryResponse,
    HistoryEvent,
)
from agentsmithy_server.core.project import Project
from agentsmithy_server.dialogs.storages.file_edits import DialogFileEditStorage
from agentsmithy_server.dialogs.storages.reasoning import DialogReasoningStorage
from agentsmithy_server.domain.events import EventType, MessageType
from agentsmithy_server.utils.logger import api_logger

router = APIRouter()


async def _build_history_response(
    project: Project, dialog_id: str, limit: int = 20, before: int | None = None
) -> DialogHistoryResponse:
    """Build complete history response as SSE event stream with cursor-based pagination.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        limit: Maximum number of events to return (default: 20)
        before: Return events before this cursor/index (exclusive).
                If None, return last `limit` events.
    """
    # Get messages from history and convert to SSE events
    base_events: list[tuple[int, HistoryEvent]] = []
    try:
        history = project.get_dialog_history(dialog_id)
        messages = history.get_messages()

        for idx, msg in enumerate(messages):
            msg_type = msg.type

            # Skip ToolMessage - those are results, not events
            if msg_type == MessageType.TOOL.value:
                continue

            # Convert LangChain types to SSE types
            if msg_type == MessageType.HUMAN.value:
                event_type = EventType.USER.value
            elif msg_type == MessageType.AI.value:
                event_type = EventType.CHAT.value
            else:
                # system, etc - keep as is
                event_type = msg_type

            # Get content as string
            content_str = (
                msg.content if isinstance(msg.content, str) else str(msg.content)
            )

            # Skip empty AI messages (usually they only have tool_calls)
            # LLM sometimes generates AIMessage with content="" when it only wants to call tools
            # without producing text. These create empty "chat" events which aren't useful in history.
            # The tool_calls from these messages will still be added as separate "tool_call" events below.
            if msg_type == MessageType.AI.value and not content_str.strip():
                pass
            else:
                # Add message as chat/user event
                base_events.append(
                    (
                        idx,
                        HistoryEvent(
                            type=event_type,
                            content=content_str,
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
                                    type=EventType.TOOL_CALL.value,
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
                            type=EventType.REASONING.value,
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

    # Get file edit events
    file_edit_events: list[tuple[int, HistoryEvent]] = []
    try:
        with DialogFileEditStorage(project, dialog_id) as storage:
            edits = storage.get_all()
            for edit in edits:
                file_edit_events.append(
                    (
                        edit.message_index,
                        HistoryEvent(
                            type=EventType.FILE_EDIT.value,
                            file=edit.file,
                            diff=edit.diff,
                            checkpoint=edit.checkpoint,
                        ),
                    )
                )
    except Exception as e:
        api_logger.error(
            "Failed to load file edits",
            exc_info=True,
            error=str(e),
            dialog_id=dialog_id,
        )

    # Merge all events and sort
    # For same index: reasoning (type=0) comes before other events (type=1)
    all_events = base_events + reasoning_events + file_edit_events
    all_events.sort(
        key=lambda x: (x[0], 0 if x[1].type == EventType.REASONING.value else 1)
    )

    # Assign global indices to all events in chronological order
    for idx, (_, evt) in enumerate(all_events):
        evt.idx = idx

    # Total count of events
    total_count = len(all_events)

    # Apply cursor-based pagination
    if before is not None:
        # Get `limit` events before cursor
        end_pos = before
        start_pos = max(0, end_pos - limit)
        paginated_events = all_events[start_pos:end_pos]
    else:
        # Get last `limit` events (default behavior)
        start_pos = max(0, total_count - limit)
        paginated_events = all_events[start_pos:]

    # Extract events in sorted order (already chronological)
    events_data: list[HistoryEvent] = [evt for _, evt in paginated_events]

    # Determine pagination metadata
    if events_data:
        first_idx: int = (
            events_data[0].idx or 0
        )  # idx is always set above, but need type hint
        last_idx: int = events_data[-1].idx or 0
        has_more = first_idx > 0
    else:
        first_idx = 0
        last_idx = 0
        has_more = False

    return DialogHistoryResponse(
        dialog_id=dialog_id,
        events=events_data,
        total_events=total_count,
        has_more=has_more,
        first_idx=first_idx,
        last_idx=last_idx,
    )


@router.get("/api/dialogs/{dialog_id}/history", response_model_exclude_none=True)
async def get_dialog_history(
    dialog_id: str,
    limit: int = 20,
    before: int | None = None,
    project: Project = Depends(get_project),  # noqa: B008
) -> DialogHistoryResponse:
    """Get dialog history with cursor-based pagination.

    By default returns the last 20 events in chronological order.
    Use `before` cursor to load previous pages (e.g., when scrolling up).

    Args:
        dialog_id: Dialog identifier
        limit: Maximum number of events to return (default: 20)
        before: Cursor - return events before this index (for pagination when scrolling up)

    Returns:
        Dialog history as SSE events (same format as streaming) with pagination metadata

    Example usage:
        # Get last 20 events
        GET /api/dialogs/{dialog_id}/history?limit=20

        # Get 20 events before index 80 (scroll up)
        GET /api/dialogs/{dialog_id}/history?limit=20&before=80

    Example response:
        {
            "dialog_id": "01J...",
            "events": [
                {"type": "user", "content": "read file.txt", "idx": 0},
                {"type": "reasoning", "content": "I need to read...", "idx": 1},
                {"type": "chat", "content": "I'll read the file...", "idx": 2},
                {"type": "tool_call", "name": "read_file", "args": {"path": "file.txt"}, "idx": 3},
                {"type": "chat", "content": "File contains...", "idx": 4}
            ],
            "total_events": 100,
            "has_more": true,
            "first_idx": 80,
            "last_idx": 99
        }
    """
    api_logger.info(
        "Fetching dialog history",
        dialog_id=dialog_id,
        limit=limit,
        before=before,
    )

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
        response = await _build_history_response(project, dialog_id, limit, before)
        api_logger.info(
            "Dialog history retrieved",
            dialog_id=dialog_id,
            total_events=response.total_events,
            returned_events=len(response.events),
            has_more=response.has_more,
        )
        return response
    except Exception as e:
        api_logger.error(
            "Failed to build history response", exc_info=True, error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
