"""API request/response and dialog schemas.

Extracted from `agentsmithy_server.api.server` without behavior changes to
enable router/service refactors.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    context: dict[str, Any] = {}
    stream: bool = True
    dialog_id: str | None = None


class ChatResponse(BaseModel):
    content: str
    done: bool = False
    metadata: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "agentsmithy-server"


class DialogCreateRequest(BaseModel):
    title: str | None = None
    set_current: bool = True


class DialogPatchRequest(BaseModel):
    title: str | None = None


class DialogListParams(BaseModel):
    sort: str = "updated_at"  # created_at|updated_at
    order: str = "desc"  # asc|desc
    limit: int | None = 50
    offset: int = 0


class ToolResultResponse(BaseModel):
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any]
    timestamp: str
    metadata: dict[str, Any] = {}


class HistoryMessage(BaseModel):
    """A single message in dialog history."""

    type: str  # human, ai, system, tool, reasoning
    content: str
    index: int  # Position in history
    timestamp: str | None = None
    # For AI messages with tool calls
    tool_calls: list[dict[str, Any]] | None = None
    # For reasoning messages
    reasoning_id: int | None = None
    model_name: str | None = None


class ToolCallInfo(BaseModel):
    """Information about a tool call execution."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    result_preview: str  # Short preview of result
    has_full_result: bool  # Whether full result is stored
    timestamp: str
    message_index: int  # Link to message that triggered it


class DialogHistoryResponse(BaseModel):
    """Complete dialog history with messages (including reasoning inline) and tool calls."""

    dialog_id: str
    messages: list[HistoryMessage]  # Includes reasoning as type="reasoning"
    tool_calls: list[ToolCallInfo]
    total_messages: int  # Total including reasoning
    total_reasoning: int
    total_tool_calls: int
