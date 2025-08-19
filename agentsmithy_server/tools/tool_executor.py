from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Dict, List
import json

from langchain_core.messages import BaseMessage, ToolMessage

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
        """Non-streaming path using iterative tool loop until completion."""
        bound_llm = self._bind_tools()
        conversation: List[BaseMessage] = list(messages)
        aggregated_tool_results: List[dict[str, Any]] = []
        aggregated_tool_calls: List[dict[str, Any]] = []

        while True:
            response = await bound_llm.ainvoke(conversation)
            tool_calls = getattr(response, "tool_calls", [])

            if not tool_calls:
                # Completed text answer. If tools were used, return structured tool_response
                final_content = getattr(response, "content", "")
                if aggregated_tool_results:
                    return {
                        "type": "tool_response",
                        "content": final_content,
                        "tool_calls": aggregated_tool_calls,
                        "tool_results": aggregated_tool_results,
                    }
                return {"type": "text", "content": final_content}

            # Execute tools one-by-one, append ToolMessages to conversation
            for call in tool_calls:
                name = call.get("name") or call.get("tool", {}).get("name")
                args = call.get("args") or call.get("tool", {}).get("args") or {}
                if not name:
                    continue
                result = await self.tool_manager.run_tool(name, **args)
                aggregated_tool_results.append({"name": name, "result": result})
                aggregated_tool_calls.append({"name": name, "args": args})

                # Append ToolMessage with serialized result back to model
                tool_message = ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call.get("id", ""),
                )
                conversation.append(tool_message)

    async def _process_streaming(self, messages: List[BaseMessage]) -> AsyncGenerator[Any, None]:
        """Streaming loop: emit tool_result events as they happen, then final content."""
        bound_llm = self._bind_tools()
        conversation: List[BaseMessage] = list(messages)

        while True:
            # For simplicity, do non-chunked model call per iteration
            response = await bound_llm.ainvoke(conversation)
            tool_calls = getattr(response, "tool_calls", [])
            if not tool_calls:
                final_text = getattr(response, "content", "")
                if final_text:
                    yield {"content": final_text}
                break

            for call in tool_calls:
                name = call.get("name") or call.get("tool", {}).get("name")
                args = call.get("args") or call.get("tool", {}).get("args") or {}
                if not name:
                    continue
                result = await self.tool_manager.run_tool(name, **args)
                yield {"type": "tool_result", "name": name, "result": result}
                tool_message = ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call.get("id", ""),
                )
                conversation.append(tool_message)



