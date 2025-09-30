from __future__ import annotations

from typing import Any


def error(
    tool: str,
    code: str,
    message: str,
    *,
    error_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard error envelope for tools.

    Example:
    {"type": "error", "tool": "web_search", "code": "rate_limited", "message": "..."}
    """
    payload: dict[str, Any] = {
        "type": "error",
        "tool": tool,
        "code": code,
        "message": message,
    }
    if error_type:
        payload["error_type"] = error_type
    if details:
        payload["details"] = details
    return payload


def not_found(
    tool: str,
    resource: str,
    resource_id: str,
    *,
    hint: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard not-found envelope as an error with code=not_found.

    Example:
    {"type": "error", "tool": "get_tool_result", "code": "not_found", "resource": "tool_result", "id": "..."}
    """
    payload: dict[str, Any] = {
        "type": "error",
        "tool": tool,
        "code": "not_found",
        "resource": resource,
        "id": resource_id,
    }
    if hint:
        payload["hint"] = hint
    if extra:
        payload.update(extra)
    return payload
