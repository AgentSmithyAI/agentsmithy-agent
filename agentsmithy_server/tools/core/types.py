from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# Public types this module exports
__all__ = [
    "ToolError",
    "ToolResult",
]


class ToolError(BaseModel):
    type: Literal["tool_error"] = "tool_error"
    name: str
    error: str
    error_type: str | None = None


class ToolResult(BaseModel):
    type: str = "success"
    name: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
