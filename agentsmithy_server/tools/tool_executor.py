from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage

from agentsmithy_server.core.llm_provider import LLMProvider
from agentsmithy_server.utils.logger import agent_logger

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

    def process_with_tools(
        self, messages: list[BaseMessage], stream: bool = True
    ) -> AsyncGenerator[Any, None]:
        """Streaming path: yield strings or structured dicts suitable for SSE."""
        return self._process_streaming(messages)

    async def process_with_tools_async(
        self, messages: list[BaseMessage]
    ) -> dict[str, Any]:
        """Non-streaming path using iterative tool loop until completion."""
        bound_llm = self._bind_tools()
        conversation: list[BaseMessage] = list(messages)
        aggregated_tool_results: list[dict[str, Any]] = []
        aggregated_tool_calls: list[dict[str, Any]] = []

        while True:
            agent_logger.info("LLM invoke", messages=len(conversation))
            response = await bound_llm.ainvoke(conversation)
            tool_calls = getattr(response, "tool_calls", [])
            agent_logger.info("LLM response", has_tool_calls=bool(tool_calls))

            if not tool_calls:
                # Completed text answer. If tools were used, return structured tool_response
                final_content = getattr(response, "content", "")
                if aggregated_tool_results:
                    return {
                        "type": "tool_response",
                        "content": final_content,
                        "tool_calls": aggregated_tool_calls,
                        "tool_results": aggregated_tool_results,
                        "conversation": conversation,  # Return full conversation for history
                    }
                return {
                    "type": "text",
                    "content": final_content,
                    "conversation": conversation,
                }

            # Execute tools one-by-one, append ToolMessages to conversation
            # IMPORTANT: append the AI response (with tool_calls) first per OpenAI spec
            conversation.append(response)
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

    async def _process_streaming(
        self, messages: list[BaseMessage]
    ) -> AsyncGenerator[Any, None]:
        """Streaming loop: emit content chunks and tool results as they happen."""
        bound_llm = self._bind_tools()
        conversation: list[BaseMessage] = list(messages)

        while True:
            agent_logger.info("LLM streaming", messages=len(conversation))
            
            # Use astream for true streaming
            accumulated_content = ""
            accumulated_tool_calls: list[dict] = []
            current_tool_call: dict | None = None
            
            async for chunk in bound_llm.astream(conversation):
                # Handle content chunks
                content = getattr(chunk, "content", None)
                if content:
                    content_str = ""
                    
                    # LangChain may return content as a list of dicts for newer models
                    if isinstance(content, list):
                        # Extract text from each content item
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                content_str += item["text"]
                            elif isinstance(item, str):
                                content_str += item
                            else:
                                content_str += str(item)
                    elif isinstance(content, dict):
                        # Handle structured content
                        content_str = content.get("text", str(content))
                    elif isinstance(content, str):
                        content_str = content
                    else:
                        content_str = str(content)
                    
                    # Only yield non-empty content
                    if content_str:
                        accumulated_content += content_str
                        # Yield chat chunk in simplified protocol
                        yield {"type": "chat", "content": content_str}
                
                # Handle tool call chunks
                tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                for tc_chunk in tool_call_chunks:
                    # Start a new tool call
                    if tc_chunk.get("index") is not None:
                        if current_tool_call and "name" in current_tool_call:
                            accumulated_tool_calls.append(current_tool_call)
                        current_tool_call = {
                            "index": tc_chunk["index"],
                            "id": tc_chunk.get("id", ""),
                            "name": tc_chunk.get("name", ""),
                            "args": tc_chunk.get("args", ""),
                        }
                    # Accumulate tool call data
                    elif current_tool_call:
                        if tc_chunk.get("name"):
                            current_tool_call["name"] += tc_chunk["name"]
                        if tc_chunk.get("args"):
                            current_tool_call["args"] += tc_chunk["args"]
            
            # Add the last tool call if exists
            if current_tool_call and "name" in current_tool_call:
                accumulated_tool_calls.append(current_tool_call)
            
            # If no tool calls, we're done
            if not accumulated_tool_calls:
                # Stream might have already yielded all content chunks
                break
            
            # Create AI message with tool calls for conversation history
            from langchain_core.messages import AIMessage
            ai_message = AIMessage(content=accumulated_content or "")
            ai_message.tool_calls = []
            
            # Execute tools and stream results
            for tool_call in accumulated_tool_calls:
                try:
                    # Parse accumulated args string to dict
                    args = json.loads(tool_call.get("args", "{}"))
                    name = tool_call.get("name", "")
                    tool_id = tool_call.get("id", "")
                    
                    if not name:
                        continue
                    
                    # Add to AI message for history
                    ai_message.tool_calls.append({
                        "name": name,
                        "args": args,
                        "id": tool_id
                    })
                    
                    # Emit tool_call event for SSE
                    if self._sse_callback is not None:
                        await self.emit_event({
                            "type": "tool_call",
                            "name": name,
                            "args": args,
                        })

                    # Execute tool
                    result = await self.tool_manager.run_tool(name, **args)
                    
                    # Optionally emit file_edit when result includes file path
                    if isinstance(result, dict) and "path" in result:
                        await self.emit_event({
                            "type": "file_edit",
                            "file": result.get("path"),
                        })
                    
                    # Add tool message to conversation
                    tool_message = ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_id,
                    )
                    conversation.append(tool_message)
                    
                except json.JSONDecodeError:
                    agent_logger.error("Failed to parse tool args", args=tool_call.get("args"))
                except Exception as e:
                    agent_logger.error("Tool execution failed", error=str(e))
            
            # Add AI message with tool calls to conversation
            conversation.append(ai_message)
