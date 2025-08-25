from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool as LCBaseTool

SseCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BaseTool(LCBaseTool, ABC):  # type: ignore[override]
    """Base class for server-side tools.

    Tools receive validated arguments and can emit SSE-compatible events via
    the provided callback. Subclasses should implement `arun`.
    """

    # Tool subclasses should declare: name: str, description: str, args_schema: type[BaseModel]

    def __init__(self) -> None:
        self._sse_callback: SseCallback | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback

    async def emit_event(self, event: dict[str, Any]) -> None:
        if self._sse_callback is not None:
            await self._sse_callback(event)

    # Match LC BaseTool coroutine signature to satisfy type checker
    async def arun(self, tool_input: str | dict[Any, Any] | None = None, **kwargs: Any) -> Any:  # type: ignore[override]
        """Execute tool asynchronously. Default calls LangChain _arun hook."""
        merged_kwargs: dict[Any, Any] = {}
        if isinstance(tool_input, dict):
            merged_kwargs.update(tool_input)
        merged_kwargs.update(kwargs)
        return await self._arun(**merged_kwargs)

    # Provide a default _run so subclasses are not abstract for mypy
    def _run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError("Synchronous run is not supported; use arun")
