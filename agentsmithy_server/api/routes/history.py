"""History endpoint: retrieve complete dialog history with reasoning and tool calls."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import BaseMessage

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


# Event ordering priorities - lower number means earlier in the stream
class EventPriority:
    """Priority constants for ordering events within a message group."""

    REASONING = 0  # Reasoning blocks come first
    MESSAGE = 1  # Then the message itself
    TOOL_CALL = 2  # Then tool calls
    FILE_EDIT = 3  # Then file edits
    ORPHAN = 4  # Orphan reasoning at the very end


@dataclass
class EventSortKey:
    """Sort key for ordering events chronologically."""

    db_index: int  # Database index (message position)
    priority: int  # Event type priority
    sub_index: int = 0  # Sub-index for multiple events of same type

    def to_tuple(self) -> tuple[int, int, int]:
        """Convert to tuple for sorting."""
        return (self.db_index, self.priority, self.sub_index)


@dataclass
class MessagesData:
    """Container for loaded messages and their metadata."""

    messages: list[BaseMessage]
    original_indices: list[int]
    db_ids: list[int]
    total_visible: int
    start_pos: int
    end_pos: int
    has_more: bool


def _load_messages(
    project: Project, dialog_id: str, limit: int, before: int | None
) -> MessagesData:
    """Load messages slice with pagination metadata.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        limit: Maximum number of messages to return
        before: Return messages before this index (exclusive)

    Returns:
        MessagesData with loaded messages and metadata
    """
    try:
        history = project.get_dialog_history(dialog_id)
        total_visible = history.get_messages_count()

        # Calculate slice range for visible messages
        if before is not None:
            end_pos = before
            start_pos = max(0, end_pos - limit)
        else:
            end_pos = total_visible
            start_pos = max(0, end_pos - limit)

        messages, original_indices, message_db_ids = history.get_messages_slice(
            start_pos, end_pos
        )
        has_more = start_pos > 0

        return MessagesData(
            messages=messages,
            original_indices=original_indices,
            db_ids=message_db_ids,
            total_visible=total_visible,
            start_pos=start_pos,
            end_pos=end_pos,
            has_more=has_more,
        )
    except Exception as e:
        api_logger.error(
            "Failed to load messages", exc_info=True, error=str(e), dialog_id=dialog_id
        )
        return MessagesData(
            messages=[],
            original_indices=[],
            db_ids=[],
            total_visible=0,
            start_pos=0,
            end_pos=0,
            has_more=False,
        )


def _load_reasoning(
    project: Project, dialog_id: str, message_indices: set[int], before: int | None
) -> tuple[dict[int, list[HistoryEvent]], list[HistoryEvent]]:
    """Load reasoning blocks for selected messages.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        message_indices: Set of message indices to load reasoning for
        before: Pagination cursor (None means loading from end)

    Returns:
        Tuple of (reasoning_by_msg_idx, orphan_reasoning)
    """
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

            # Load orphan reasoning (message_index=-1) only when loading the END of history
            if before is None:
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

    return reasoning_by_msg_idx, orphan_reasoning


def _load_file_edits(
    project: Project, dialog_id: str, message_indices: set[int]
) -> dict[int, list[HistoryEvent]]:
    """Load file edits for selected messages.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        message_indices: Set of message indices to load edits for

    Returns:
        Dictionary mapping message index to list of file edit events
    """
    file_edits_by_msg_idx: dict[int, list[HistoryEvent]] = {}

    try:
        with DialogFileEditStorage(project, dialog_id) as storage:
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

    return file_edits_by_msg_idx


def _is_empty_ai_message(msg: BaseMessage) -> bool:
    """Check if message is an empty AI message (no content text)."""
    if msg.type != MessageType.AI.value:
        return False
    content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
    return not content_str.strip()


def _extract_tool_calls(msg: BaseMessage) -> list[HistoryEvent]:
    """Extract tool call events from a message.

    Args:
        msg: Message to extract tool calls from

    Returns:
        List of tool call events
    """
    tool_call_events = []
    try:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
                tc_name = (
                    tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                )
                tc_args = (
                    tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                )

                tool_call_events.append(
                    HistoryEvent(
                        type=EventType.TOOL_CALL.value,
                        id=tc_id,
                        name=tc_name,
                        args=tc_args,
                    )
                )
    except Exception:
        pass

    return tool_call_events


def _build_events_stream(
    messages_data: MessagesData,
    reasoning_by_msg_idx: dict[int, list[HistoryEvent]],
    file_edits_by_msg_idx: dict[int, list[HistoryEvent]],
    orphan_reasoning: list[HistoryEvent],
) -> list[HistoryEvent]:
    """Build chronologically ordered event stream from all data sources.

    Args:
        messages_data: Loaded messages with metadata
        reasoning_by_msg_idx: Reasoning blocks indexed by message
        file_edits_by_msg_idx: File edits indexed by message
        orphan_reasoning: Orphan reasoning blocks (not linked to messages)

    Returns:
        List of events in chronological order
    """
    all_events_with_sort: list[tuple[EventSortKey, HistoryEvent]] = []
    non_empty_count = 0  # Track sequential index for non-empty messages only

    # Process each message and its related events
    for msg, db_idx, _msg_db_id in zip(
        messages_data.messages,
        messages_data.original_indices,
        messages_data.db_ids,
        strict=False,
    ):
        # Skip ToolMessage - already filtered by SQL
        if msg.type == MessageType.TOOL.value:
            continue

        is_empty_ai = _is_empty_ai_message(msg)

        # 1. Add reasoning blocks (come before message)
        if db_idx in reasoning_by_msg_idx:
            for idx, reasoning_event in enumerate(reasoning_by_msg_idx[db_idx]):
                sort_key = EventSortKey(
                    db_index=db_idx, priority=EventPriority.REASONING, sub_index=idx
                )
                all_events_with_sort.append((sort_key, reasoning_event))

        # 2. Add message event (only for non-empty messages)
        if not is_empty_ai:
            # Determine event type
            if msg.type == MessageType.HUMAN.value:
                event_type = EventType.USER.value
            elif msg.type == MessageType.AI.value:
                event_type = EventType.CHAT.value
            else:
                event_type = msg.type

            content_str = (
                msg.content if isinstance(msg.content, str) else str(msg.content)
            )

            # Only user and chat messages get idx (for pagination)
            if event_type in (EventType.USER.value, EventType.CHAT.value):
                client_idx = messages_data.start_pos + non_empty_count
                non_empty_count += 1
                message_event = HistoryEvent(
                    type=event_type,
                    content=content_str,
                    idx=client_idx,
                )
            else:
                # Other message types (system, tool) don't get idx
                message_event = HistoryEvent(
                    type=event_type,
                    content=content_str,
                )

            sort_key = EventSortKey(db_index=db_idx, priority=EventPriority.MESSAGE)
            all_events_with_sort.append((sort_key, message_event))

        # 3. Add tool calls (come after message)
        tool_call_events = _extract_tool_calls(msg)
        for idx, tool_event in enumerate(tool_call_events):
            sort_key = EventSortKey(
                db_index=db_idx, priority=EventPriority.TOOL_CALL, sub_index=idx
            )
            all_events_with_sort.append((sort_key, tool_event))

        # 4. Add file edits (come after tool calls)
        if db_idx in file_edits_by_msg_idx:
            for idx, edit_event in enumerate(file_edits_by_msg_idx[db_idx]):
                sort_key = EventSortKey(
                    db_index=db_idx, priority=EventPriority.FILE_EDIT, sub_index=idx
                )
                all_events_with_sort.append((sort_key, edit_event))

    # 5. Add orphan reasoning at the end
    orphan_db_idx = (
        max(messages_data.original_indices) + 1 if messages_data.original_indices else 0
    )
    for idx, orphan_event in enumerate(orphan_reasoning):
        sort_key = EventSortKey(
            db_index=orphan_db_idx, priority=EventPriority.ORPHAN, sub_index=idx
        )
        all_events_with_sort.append((sort_key, orphan_event))

    # Sort events chronologically
    all_events_with_sort.sort(key=lambda x: x[0].to_tuple())

    # Extract just the events
    return [event for _, event in all_events_with_sort]


def _calculate_pagination_metadata(
    events: list[HistoryEvent],
) -> tuple[int, int]:
    """Calculate first_idx and last_idx from events.

    Args:
        events: List of events

    Returns:
        Tuple of (first_idx, last_idx)
    """
    message_events_with_idx = [e for e in events if e.idx is not None]
    if message_events_with_idx:
        first_idx = message_events_with_idx[0].idx or 0
        last_idx = message_events_with_idx[-1].idx or 0
    else:
        first_idx = 0
        last_idx = 0

    return first_idx, last_idx


async def _build_history_response(
    project: Project, dialog_id: str, limit: int = 20, before: int | None = None
) -> DialogHistoryResponse:
    """Build complete history response with cursor-based pagination on messages.

    This function orchestrates loading messages, reasoning, and file edits,
    then builds a chronologically ordered event stream.

    Args:
        project: Project instance
        dialog_id: Dialog identifier
        limit: Maximum number of messages to return (default: 20)
        before: Return messages before this index (exclusive).
                If None, return last `limit` messages.

    Returns:
        DialogHistoryResponse with paginated events and metadata
    """
    # Step 1: Load messages with pagination
    messages_data = _load_messages(project, dialog_id, limit, before)
    message_indices = set(messages_data.original_indices)

    # Step 2: Load reasoning blocks for the selected messages
    reasoning_by_msg_idx, orphan_reasoning = _load_reasoning(
        project, dialog_id, message_indices, before
    )

    # Step 3: Load file edits for the selected messages
    file_edits_by_msg_idx = _load_file_edits(project, dialog_id, message_indices)

    # Step 4: Build chronologically ordered event stream
    events = _build_events_stream(
        messages_data, reasoning_by_msg_idx, file_edits_by_msg_idx, orphan_reasoning
    )

    # Step 5: Calculate pagination metadata
    first_idx, last_idx = _calculate_pagination_metadata(events)

    return DialogHistoryResponse(
        dialog_id=dialog_id,
        events=events,
        total_events=messages_data.total_visible,
        has_more=messages_data.has_more,
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
