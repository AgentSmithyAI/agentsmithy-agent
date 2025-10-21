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


class DialogMetadata(BaseModel):
    """Dialog metadata for API responses."""

    id: str
    title: str | None = None
    created_at: str
    updated_at: str


class DialogListResponse(BaseModel):
    """Response for GET /api/dialogs."""

    current_dialog_id: str | None = None
    dialogs: list[DialogMetadata]


class DialogMetadataResponse(BaseModel):
    """Response for GET /api/dialogs/{dialog_id}."""

    id: str
    title: str | None = None
    created_at: str
    updated_at: str


class CurrentDialogResponse(BaseModel):
    """Response for GET /api/dialogs/current."""

    id: str | None = None
    meta: DialogMetadata | None = None


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


class HistoryEvent(BaseModel):
    """A single event in dialog history (same as SSE events)."""

    type: str  # user, chat, reasoning, tool_call, file_edit
    idx: int | None = None  # Event index in the full history
    # For user/chat/reasoning
    content: str | None = None
    # For reasoning
    model_name: str | None = None
    # For tool_call
    id: str | None = None  # tool_call_id
    name: str | None = None
    args: dict[str, Any] | None = None
    # For file_edit
    file: str | None = None
    diff: str | None = None
    checkpoint: str | None = None


class DialogHistoryResponse(BaseModel):
    """Complete dialog history as event stream (SSE replay)."""

    dialog_id: str
    events: list[HistoryEvent]  # Chronological event stream
    total_events: (
        int  # Total count of ALL events: messages + reasoning + tool_calls + file_edits
    )
    has_more: bool  # Whether there are more events before the returned ones
    first_idx: int  # Index of the first event in the returned list
    last_idx: int  # Index of the last event in the returned list
