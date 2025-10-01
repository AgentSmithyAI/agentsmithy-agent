from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# Public types this module exports
__all__ = [
    "ToolError",
    "ToolResult",
    "parse_tool_result",
]


class ToolError(BaseModel):
    """Standard error result for all tools.

    Use isinstance(result, ToolError) to check for errors.
    """

    type: Literal["tool_error"] = "tool_error"
    name: str
    code: str
    error: str
    error_type: str | None = None
    details: dict[str, Any] | None = None


class ToolResult(BaseModel):
    type: str = "success"
    name: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def parse_tool_result[TSuccess: BaseModel](
    result: dict[str, Any], success_type: type[TSuccess]
) -> TSuccess | ToolError:
    """Parse tool result dict into typed Pydantic model.

    Returns either the success type or ToolError.

    Example:
        r = parse_tool_result(result, ReadFileSuccess)
        if isinstance(r, ToolError):
            return f"Error: {r.error}"
        return f"Content: {r.content}"
    """
    if result.get("type") == "tool_error":
        return ToolError.model_validate(result)
    return success_type.model_validate(result)
