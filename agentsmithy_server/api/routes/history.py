"""History endpoint: retrieve complete dialog history with reasoning and tool calls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agentsmithy_server.api.deps import get_project
from agentsmithy_server.api.schemas import (
    DialogHistoryResponse,
    HistoryMessage,
)
from agentsmithy_server.core.dialog_reasoning_storage import DialogReasoningStorage
from agentsmithy_server.core.project import Project
from agentsmithy_server.utils.logger import api_logger

router = APIRouter()


async def _build_history_response(
    project: Project, dialog_id: str
) -> DialogHistoryResponse:
    """Build complete history response as event stream."""
    # Get messages from history
    base_messages: list[tuple[int, HistoryMessage]] = []
    try:
        history = project.get_dialog_history(dialog_id)
        messages = history.get_messages()

        for idx, msg in enumerate(messages):
            # Add regular message
            base_messages.append(
                (
                    idx,
                    HistoryMessage(
                        type=msg.type,
                        content=(
                            msg.content
                            if isinstance(msg.content, str)
                            else str(msg.content)
                        ),
                    ),
                )
            )

            # Extract tool_calls and add as separate events
            try:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
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
                        base_messages.append(
                            (
                                idx,  # Same position as AI message
                                HistoryMessage(
                                    type="tool_call",
                                    tool_name=tc_name,
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

    # Get reasoning blocks and merge into messages
    reasoning_count = 0
    reasoning_messages: list[tuple[int, HistoryMessage]] = []
    try:
        with DialogReasoningStorage(project, dialog_id) as storage:
            blocks = storage.get_all()
            for block in blocks:
                # Create reasoning message to insert before related message
                reasoning_messages.append(
                    (
                        block.message_index,  # Sort key - insert before this message
                        HistoryMessage(
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

    # Merge base messages and reasoning, sort by message_index
    # For same index: reasoning (type=0) comes before regular message (type=1)
    all_messages = base_messages + reasoning_messages
    all_messages.sort(key=lambda x: (x[0], 0 if x[1].type == "reasoning" else 1))

    # Extract messages in sorted order (already sorted by message_index)
    messages_data: list[HistoryMessage] = [msg for _, msg in all_messages]

    # Count tool calls from messages
    tool_calls_count = sum(1 for msg in messages_data if msg.type == "tool_call")

    return DialogHistoryResponse(
        dialog_id=dialog_id,
        messages=messages_data,
        total_messages=len(messages_data),
        total_reasoning=reasoning_count,
        total_tool_calls=tool_calls_count,
    )


@router.get("/api/dialogs/{dialog_id}/history", response_model_exclude_none=True)
async def get_dialog_history(
    dialog_id: str,
    project: Project = Depends(get_project),  # noqa: B008
) -> DialogHistoryResponse:
    """Get complete history for a dialog as event stream.

    Args:
        dialog_id: Dialog identifier

    Returns:
        Complete dialog history as chronological event stream

    Example response:
        {
            "dialog_id": "01J...",
            "messages": [
                {"type": "human", "content": "read file.txt"},
                {"type": "reasoning", "content": "I need to read...", "model_name": null},
                {"type": "ai", "content": "I'll read the file..."},
                {"type": "tool_call", "tool_name": "read_file", "args": {"path": "file.txt"}},
                {"type": "ai", "content": "File contains..."}
            ],
            "total_messages": 5,
            "total_reasoning": 1,
            "total_tool_calls": 1
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
            total_events=response.total_messages,
            reasoning=response.total_reasoning,
            tool_calls=response.total_tool_calls,
        )
        return response
    except Exception as e:
        api_logger.error(
            "Failed to build history response", exc_info=True, error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
