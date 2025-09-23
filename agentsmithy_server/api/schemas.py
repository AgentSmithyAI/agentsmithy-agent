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
