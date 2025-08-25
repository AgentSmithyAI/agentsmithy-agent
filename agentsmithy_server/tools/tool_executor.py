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
        # Optional SSE callback to emit structured events upstream if needed
        self._sse_callback = None

    def set_sse_callback(self, callback):
        self._sse_callback = callback

    async def emit_event(self, event: dict[str, Any]) -> None:
        if self._sse_callback is not None:
            try:
                await self._sse_callback(event)
            except Exception as e:
                agent_logger.error(
                    "Failed to emit SSE event from ToolExecutor", error=str(e)
                )

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

            # Boundary markers for chat and reasoning
            chat_started = False
            reasoning_started = False

            async for chunk in bound_llm.astream(conversation):
                # Try to extract reasoning from provider-specific metadata (minimal and robust)
                try:
                    additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
                    response_metadata = getattr(chunk, "response_metadata", {}) or {}
                    reasoning = None
                    if isinstance(additional_kwargs, dict):
                        reasoning = additional_kwargs.get("reasoning")
                    if reasoning is None and isinstance(response_metadata, dict):
                        reasoning = response_metadata.get("reasoning")

                    reasoning_text = None
                    if isinstance(reasoning, str):
                        reasoning_text = reasoning
                    elif isinstance(reasoning, dict):
                        summary = reasoning.get("summary")
                        if isinstance(summary, str):
                            reasoning_text = summary
                        elif isinstance(summary, list) and summary:
                            parts: list[str] = []
                            for item in summary:
                                if isinstance(item, dict):
                                    if isinstance(item.get("text"), str):
                                        parts.append(item.get("text"))
                                    elif isinstance(item.get("content"), list):
                                        for sub in item.get("content"):
                                            if isinstance(sub, dict) and isinstance(
                                                sub.get("text"), str
                                            ):
                                                parts.append(sub.get("text"))
                            if parts:
                                reasoning_text = "".join(parts)
                        elif isinstance(summary, dict):
                            if isinstance(summary.get("text"), str):
                                reasoning_text = summary.get("text")
                            elif isinstance(summary.get("content"), list):
                                parts2: list[str] = []
                                for sub in summary.get("content"):
                                    if isinstance(sub, dict) and isinstance(
                                        sub.get("text"), str
                                    ):
                                        parts2.append(sub.get("text"))
                                if parts2:
                                    reasoning_text = "".join(parts2)
                        if not reasoning_text and isinstance(
                            reasoning.get("content"), str
                        ):
                            reasoning_text = reasoning.get("content")

                    if reasoning_text:
                        if not reasoning_started:
                            reasoning_started = True
                            yield {"type": "reasoning_start"}
                        yield {"type": "reasoning", "content": reasoning_text}
                except Exception:
                    pass

                # Handle content chunks
                content = getattr(chunk, "content", None)
                if content:
                    # Only process actual text content
                    if isinstance(content, str):
                        if not chat_started:
                            chat_started = True
                            yield {"type": "chat_start"}
                        accumulated_content += content
                        yield {"type": "chat", "content": content}
                    elif isinstance(content, list):
                        # LangChain may return content as list of dicts for newer models
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                text_parts.append(item["text"])
                            elif isinstance(item, str):
                                text_parts.append(item)
                        if text_parts:
                            if not chat_started:
                                chat_started = True
                                yield {"type": "chat_start"}
                            text = "".join(text_parts)
                            accumulated_content += text
                            yield {"type": "chat", "content": text}

                # Handle tool call chunks
                tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                for tc_chunk in tool_call_chunks:
                    # Check if we need to start a new tool call or continue existing one
                    chunk_index = tc_chunk.get("index")
                    if chunk_index is not None:
                        # Check if this is a continuation of current tool call
                        if (
                            current_tool_call
                            and current_tool_call.get("index") == chunk_index
                        ):
                            # Continue accumulating the same tool call
                            if tc_chunk.get("id") and not current_tool_call.get("id"):
                                current_tool_call["id"] = tc_chunk["id"]
                            if tc_chunk.get("name"):
                                current_tool_call["name"] += tc_chunk["name"]
                            if tc_chunk.get("args"):
                                current_tool_call["args"] += tc_chunk["args"]
                        else:
                            # New tool call
                            if current_tool_call and "name" in current_tool_call:
                                accumulated_tool_calls.append(current_tool_call)
                            current_tool_call = {
                                "index": chunk_index,
                                "id": tc_chunk.get("id", ""),
                                "name": tc_chunk.get("name", ""),
                                "args": tc_chunk.get("args", ""),
                            }
                    # Accumulate tool call data (for chunks without index)
                    elif current_tool_call:
                        if tc_chunk.get("name"):
                            current_tool_call["name"] += tc_chunk["name"]
                        if tc_chunk.get("args"):
                            current_tool_call["args"] += tc_chunk["args"]

            # Close boundary markers at the end of this streaming chunk
            if reasoning_started:
                yield {"type": "reasoning_end"}
            if chat_started and accumulated_content:
                yield {"type": "chat_end"}

            # Add the last tool call if exists
            if (
                current_tool_call
                and "name" in current_tool_call
                and current_tool_call["name"]
            ):
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
                    name = tool_call.get("name", "")
                    tool_id = tool_call.get("id", "")

                    # Parse accumulated args string to dict
                    args_str = tool_call.get("args", "{}") or "{}"
                    # Ensure it's a string; providers stream arguments as a JSON string
                    if not isinstance(args_str, str):
                        args_str = str(args_str)

                    args = json.loads(args_str)

                    if not name:
                        continue

                    # Add to AI message for history
                    ai_message.tool_calls.append(
                        {"name": name, "args": args, "id": tool_id}
                    )

                    # Emit tool_call as a structured chunk
                    yield {"type": "tool_call", "name": name, "args": args}

                    # Execute tool
                    result = await self.tool_manager.run_tool(name, **args)

                    # Do not emit file_edit here. Mutating tools should emit their own events.

                    # Add tool message to conversation
                    tool_message = ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=tool_id,
                    )
                    conversation.append(tool_message)

                except json.JSONDecodeError as e:
                    error_msg = f"Failed to parse tool arguments: {str(e)}"
                    agent_logger.error(error_msg, tool_name=name, args_str=args_str)
                    yield {"type": "error", "error": error_msg}
                    return
                except Exception as e:
                    error_msg = f"Tool '{name}' failed: {str(e)}"
                    agent_logger.error(error_msg, tool_name=name)
                    yield {"type": "error", "error": error_msg}
                    return

            # Add AI message with tool calls to conversation
            conversation.append(ai_message)
