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
    """Build complete history response with cursor-based pagination on messages.

    Pagination is based on message indices only. Reasoning, tool_calls, and file_edits
    are loaded only for the selected messages and don't have their own indices.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        limit: Maximum number of messages to return (default: 20)
        before: Return messages before this index (exclusive).
                If None, return last `limit` messages.
    """
    # Load visible messages slice (non-ToolMessage) with their original DB indices
    # Pagination works on visible message count, SQL filters out ToolMessages
    try:
        history = project.get_dialog_history(dialog_id)
        total_visible = history.get_messages_count()  # SQL COUNT without ToolMessages

        # Calculate slice range for visible messages
        if before is not None:
            # before is a position in the visible message list (sequential index)
            end_pos = before
            start_pos = max(0, end_pos - limit)
            messages, original_indices, message_db_ids = history.get_messages_slice(
                start_pos, end_pos
            )
        else:
            # Get last `limit` visible messages
            end_pos = total_visible
            start_pos = max(0, end_pos - limit)
            messages, original_indices, message_db_ids = history.get_messages_slice(
                start_pos, end_pos
            )

        message_indices = set(original_indices)
        has_more = start_pos > 0
        total_messages = total_visible
    except Exception as e:
        api_logger.error(
            "Failed to load messages", exc_info=True, error=str(e), dialog_id=dialog_id
        )
        messages = []
        original_indices = []
        message_db_ids = []
        message_indices = set()
        total_messages = 0
        has_more = False

    # Load reasoning only for selected messages (optimized SQL query)
    reasoning_by_msg_idx: dict[int, list[HistoryEvent]] = {}
    orphan_reasoning: list[HistoryEvent] = []
    try:
        with DialogReasoningStorage(project, dialog_id) as storage:
            # Load reasoning for the selected message indices
            blocks = storage.get_for_indices(message_indices)
            for block in blocks:
                if block.message_index not in reasoning_by_msg_idx:
                    reasoning_by_msg_idx[block.message_index] = []
                reasoning_by_msg_idx[block.message_index].append(
                    HistoryEvent(
                        type=EventType.REASONING.value,
                        content=block.content,
                        model_name=block.model_name,
                    )
                )

            # Load orphan reasoning (message_index=-1) when loading the END of history
            # Orphans are current active events that haven't been linked yet
            # Show them only when we're loading the most recent messages (before=None)
            if before is None:  # Loading from the end of history
                orphan_blocks = storage.get_for_message(-1)
                for block in orphan_blocks:
                    orphan_reasoning.append(
                        HistoryEvent(
                            type=EventType.REASONING.value,
                            content=block.content,
                            model_name=block.model_name,
                        )
                    )
    except Exception as e:
        api_logger.error(
            "Failed to load reasoning",
            exc_info=True,
            error=str(e),
            dialog_id=dialog_id,
        )

    # Load file edits only for selected messages (optimized SQL query)
    file_edits_by_msg_idx: dict[int, list[HistoryEvent]] = {}
    try:
        with DialogFileEditStorage(project, dialog_id) as storage:
            # Load ONLY edits for the selected message indices
            edits = storage.get_for_indices(message_indices)
            for edit in edits:
                if edit.message_index not in file_edits_by_msg_idx:
                    file_edits_by_msg_idx[edit.message_index] = []
                file_edits_by_msg_idx[edit.message_index].append(
                    HistoryEvent(
                        type=EventType.FILE_EDIT.value,
                        file=edit.file,
                        diff=edit.diff,
                        checkpoint=edit.checkpoint,
                    )
                )
    except Exception as e:
        api_logger.error(
            "Failed to load file edits",
            exc_info=True,
            error=str(e),
            dialog_id=dialog_id,
        )

    # Build event stream: collect all events with timestamps, then sort chronologically
    # Need to gather timestamps for proper ordering

    # Collect all events with (sort_key, event)
    all_events_with_sort: list[tuple[tuple[int, str, int], HistoryEvent]] = []
    # sort_key = (db_idx, timestamp_str, priority) for stable sorting

    # Track sequential index for non-empty messages only
    non_empty_count = 0

    # Process messages: use sequential idx for client, but original DB indices for linking data
    for msg, db_idx, _msg_db_id in zip(
        messages, original_indices, message_db_ids, strict=False
    ):
        msg_type = msg.type

        # Skip ToolMessage - already filtered by SQL
        if msg_type == MessageType.TOOL.value:
            continue

        # Check if this is empty AI
        content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
        is_empty_ai = msg_type == MessageType.AI.value and not content_str.strip()

        # Collect all events for this message

        # 1. Reasoning blocks (have created_at timestamps)
        if db_idx in reasoning_by_msg_idx:
            for reasoning_event in reasoning_by_msg_idx[db_idx]:
                # Reasoning sorted by created_at, should come before message
                # Use priority 0 for reasoning
                all_events_with_sort.append(
                    ((db_idx, "0_reasoning", 0), reasoning_event)
                )

        # 2. Message event with sequential idx (only for non-empty messages)
        if not is_empty_ai:
            # Show message with idx for non-empty messages
            if msg_type == MessageType.HUMAN.value:
                event_type = EventType.USER.value
            elif msg_type == MessageType.AI.value:
                event_type = EventType.CHAT.value
            else:
                event_type = msg_type

            client_idx = start_pos + non_empty_count
            non_empty_count += 1

            message_event = HistoryEvent(
                type=event_type,
                content=content_str,
                idx=client_idx,
            )
            # Priority 1 for message
            all_events_with_sort.append(((db_idx, "1_message", 1), message_event))

        # 3. Tool calls (no timestamp, use message timestamp)
        try:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc_idx, tc in enumerate(msg.tool_calls):
                    tc_id = (
                        tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
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

                    tool_call_event = HistoryEvent(
                        type=EventType.TOOL_CALL.value,
                        id=tc_id,
                        name=tc_name,
                        args=tc_args,
                    )
                    # Priority 2 for tool_calls, sub-priority by position
                    all_events_with_sort.append(
                        ((db_idx, f"2_tool_call_{tc_idx}", 2), tool_call_event)
                    )
        except Exception:
            pass

        # 4. File edits (have created_at timestamps)
        if db_idx in file_edits_by_msg_idx:
            for edit_event in file_edits_by_msg_idx[db_idx]:
                # Priority 3 for file_edits
                all_events_with_sort.append(((db_idx, "3_file_edit", 3), edit_event))

    # 5. Orphan reasoning at the end (highest db_idx + 1)
    orphan_db_idx = max(original_indices) + 1 if original_indices else 0
    for orphan_event in orphan_reasoning:
        all_events_with_sort.append(((orphan_db_idx, "4_orphan", 4), orphan_event))

    # Sort by (db_idx, priority_string, priority_int) to maintain chronological order
    all_events_with_sort.sort(key=lambda x: x[0])

    # Extract events in sorted order
    events_data = [event for _, event in all_events_with_sort]

    # Determine pagination metadata based on messages with idx (non-empty)
    message_events_with_idx = [e for e in events_data if e.idx is not None]
    first_idx: int
    last_idx: int
    if message_events_with_idx:
        first_idx = message_events_with_idx[0].idx or 0
        last_idx = message_events_with_idx[-1].idx or 0
    else:
        first_idx = 0
        last_idx = 0

    return DialogHistoryResponse(
        dialog_id=dialog_id,
        events=events_data,
        total_events=total_messages,  # Total visible non-empty messages
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

    Pagination is based on message indices. By default returns the last 20 messages
    in chronological order with their associated reasoning, tool_calls, and file_edits.
    Use `before` cursor to load previous pages (e.g., when scrolling up).

    Only messages (user/chat) have `idx` field. Reasoning, tool_calls, and file_edits
    are attached to messages but don't have their own indices.

    Args:
        dialog_id: Dialog identifier
        limit: Maximum number of messages to return (default: 20)
        before: Cursor - return messages before this index (for pagination when scrolling up)

    Returns:
        Dialog history as SSE events (same format as streaming) with pagination metadata

    Example usage:
        # Get last 20 messages
        GET /api/dialogs/{dialog_id}/history?limit=20

        # Get 20 messages before index 80 (scroll up)
        GET /api/dialogs/{dialog_id}/history?limit=20&before=80

    Example response:
        {
            "dialog_id": "01J...",
            "events": [
                {"type": "user", "content": "read file.txt", "idx": 0},
                {"type": "reasoning", "content": "I need to read..."},
                {"type": "chat", "content": "I'll read the file...", "idx": 1},
                {"type": "tool_call", "name": "read_file", "args": {"path": "file.txt"}},
                {"type": "chat", "content": "File contains...", "idx": 2}
            ],
            "total_events": 100,
            "has_more": true,
            "first_idx": 0,
            "last_idx": 2
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
