from __future__ import annotations

from typing import Any

from .base_tool import BaseTool, SseCallback


class ToolManager:
    """Registry and lifecycle manager for tools.

    Holds tools by name, exposes a uniform `run_tool` API, and propagates SSE
    callbacks to all registered tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._sse_callback: SseCallback | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback
        for tool in self._tools.values():
            tool.set_sse_callback(callback)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        tool.set_sse_callback(self._sse_callback)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    async def run_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")
        return await tool.arun(**kwargs)
