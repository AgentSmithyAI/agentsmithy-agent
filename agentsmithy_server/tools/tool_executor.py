from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import BaseMessage

from agentsmithy_server.core.llm_provider import LLMProvider
from .tool_manager import ToolManager


class ToolExecutor:
    """Bridge between LLM tool-calls and concrete tool execution.

    Exposes two paths:
    - process_with_tools(stream=True) -> AsyncGenerator[str|dict]
    - process_with_tools_async(stream=False) -> dict
    """

    def __init__(self, tool_manager: ToolManager, llm_provider: LLMProvider) -> None:
        self.tool_manager = tool_manager
        self.llm_provider = llm_provider

    def _bind_tools(self):
        # The provider returns an LLM object with tools bound (LangChain style)
        tools = [t for t in self.tool_manager._tools.values()]
        return self.llm_provider.bind_tools(tools)

    def process_with_tools(self, messages: List[BaseMessage], stream: bool = True) -> AsyncGenerator[Any, None]:
        """Streaming path: yield strings or structured dicts suitable for SSE."""
        return self._process_streaming(messages)

    async def process_with_tools_async(self, messages: List[BaseMessage]) -> dict[str, Any]:
        """Non-streaming path: returns full aggregated result."""
        bound_llm = self._bind_tools()
        # Non-streaming: ainvoke returns full response
        response = await bound_llm.ainvoke(messages)
        content = getattr(response, "content", "")
        tool_calls = getattr(response, "tool_calls", [])

        tool_results: List[dict[str, Any]] = []
        for call in tool_calls or []:
            name = call.get("name") or call.get("tool", {}).get("name")
            args = call.get("args") or call.get("tool", {}).get("args") or {}
            if not name:
                continue
            result = await self.tool_manager.run_tool(name, **args)
            tool_results.append({"name": name, "result": result})

        if tool_results:
            return {
                "type": "tool_response",
                "content": content,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }
        return {"type": "text", "content": content}

    async def _process_streaming(self, messages: List[BaseMessage]) -> AsyncGenerator[Any, None]:
        bound_llm = self._bind_tools()
        # Streaming path: astream yields chunks; reconstruct if tool-calls appear
        async for chunk in bound_llm.astream(messages):
            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                # Execute tools immediately and emit structured events
                for call in chunk.tool_calls:
                    name = call.get("name") or call.get("tool", {}).get("name")
                    args = call.get("args") or call.get("tool", {}).get("args") or {}
                    if not name:
                        continue
                    result = await self.tool_manager.run_tool(name, **args)
                    yield {"type": "tool_result", "name": name, "result": result}
            else:
                text = getattr(chunk, "content", None)
                if text:
                    yield text



