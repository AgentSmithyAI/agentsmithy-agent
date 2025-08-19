from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool as LCBaseTool

SseCallback = Callable[[dict[str, Any]], Awaitable[None]]


class BaseTool(LCBaseTool, ABC):
    """Base class for server-side tools.

    Tools receive validated arguments and can emit SSE-compatible events via
    the provided callback. Subclasses should implement `arun`.
    """

    name: str = "tool"
    description: str = "Generic tool"

    def __init__(self) -> None:
        self._sse_callback: SseCallback | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback

    async def emit_event(self, event: dict[str, Any]) -> None:
        if self._sse_callback is not None:
            await self._sse_callback(event)

    async def arun(self, **kwargs: Any) -> dict[str, Any]:
        """Execute tool asynchronously. Default calls LangChain _arun hook."""
        return await self._arun(**kwargs)
