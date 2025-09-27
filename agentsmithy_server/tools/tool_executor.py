from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage, ToolMessage

from agentsmithy_server.core.llm_provider import LLMProvider
from agentsmithy_server.core.tool_results_storage import (
    ToolResultsStorage,
)
from agentsmithy_server.utils.logger import agent_logger

from .integration.langchain_adapter import as_langchain_tools
from .registry import ToolRegistry

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


class ToolExecutor:
    """Bridge between LLM tool-calls and concrete tool execution.

    Exposes two paths:
    - process_with_tools(stream=True) -> AsyncGenerator[str|dict]
    - process_with_tools_async(stream=False) -> dict
    """

    def __init__(self, tool_manager: ToolRegistry, llm_provider: LLMProvider) -> None:
        self.tool_manager = tool_manager
        self.llm_provider = llm_provider
        # Optional SSE callback to emit structured events upstream if needed
        self._sse_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._project: Project | None = None
        self._dialog_id: str | None = None
        # Set via set_context(...)
        self._tool_results_storage: ToolResultsStorage | None = None

    def set_sse_callback(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        self._sse_callback = callback

    def set_context(self, project: Project | None, dialog_id: str | None) -> None:
        """Set project and dialog context for tool results storage."""
        self._project = project
        self._dialog_id = dialog_id
        if project and dialog_id:
            self._tool_results_storage = ToolResultsStorage(project, dialog_id)
        else:
            self._tool_results_storage = None

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
        tools = as_langchain_tools(self.tool_manager)
        return self.llm_provider.bind_tools(tools)

    def _is_ephemeral_tool(self, name: str) -> bool:
        """Check whether a tool should be treated as ephemeral (no persistence).

        Centralizing this avoids sprinkling special-cases across flows.
        """
        try:
            tool_obj = self.tool_manager.get(name)
            return bool(getattr(tool_obj, "ephemeral", False))
        except Exception:
            return False

    async def _build_tool_message(
        self,
        tool_call_id: str,
        name: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> tuple[ToolMessage, bool]:
        """Create a ToolMessage for a tool result, optionally persisting it.

        Returns a tuple of (tool_message, is_ephemeral). When ephemeral, the
        message contains only inline results and no history/storage is written.
        """
        is_ephemeral = self._is_ephemeral_tool(name)

        # If storage is available and tool is not ephemeral, persist and build reference
        if self._tool_results_storage and not is_ephemeral:
            result_ref = await self._tool_results_storage.store_result(
                tool_call_id=tool_call_id,
                tool_name=name,
                args=args,
                result=result,
            )
            metadata = await self._tool_results_storage.get_metadata(tool_call_id)

            inline_result_json = json.dumps(result, ensure_ascii=False)
            content = {
                "tool_call_id": tool_call_id,
                "tool_name": name,
                "status": (
                    "error" if result.get("type") == "tool_error" else "success"
                ),
                "metadata": {
                    "size_bytes": metadata.size_bytes if metadata else 0,
                    "summary": metadata.summary if metadata else "",
                    "truncated_preview": self._tool_results_storage.get_truncated_preview(
                        result
                    ),
                    "result_present": True,
                    "result_length_bytes": len(inline_result_json.encode("utf-8")),
                },
                "result_ref": result_ref.to_dict(),
                "inline_result": result,
                "has_inline_result": True,
            }
            return (
                ToolMessage(
                    content=json.dumps(content, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                ),
                is_ephemeral,
            )

        # Inline-only message for ephemeral tools or when storage is unavailable
        inline_result_json = json.dumps(result, ensure_ascii=False)
        content = {
            "tool_call_id": tool_call_id,
            "tool_name": name,
            "status": ("error" if result.get("type") == "tool_error" else "success"),
            "metadata": {
                "size_bytes": len(inline_result_json.encode("utf-8")),
                "summary": "",
                "truncated_preview": None,
                "result_present": True,
                "result_length_bytes": len(inline_result_json.encode("utf-8")),
            },
            "inline_result": result,
            "has_inline_result": True,
        }
        return (
            ToolMessage(
                content=json.dumps(content, ensure_ascii=False),
                tool_call_id=tool_call_id,
            ),
            True,
        )

    def _append_tool_message_to_history(self, tool_message: ToolMessage) -> None:
        """Persist a slim reference-only ToolMessage to dialog history.

        The saved message will exclude any inline result or truncated preview and
        contain only a reference and length so that history stays compact.
        """
        try:
            if not (
                self._project
                and self._dialog_id
                and hasattr(self._project, "get_dialog_history")
            ):
                return

            # Build a minimized envelope
            content = tool_message.content
            slim_content: dict[str, Any] | None = None
            try:
                if isinstance(content, str):
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "result_ref" in parsed:
                        metadata = parsed.get("metadata", {}) or {}
                        size_bytes = metadata.get("size_bytes", 0)
                        slim_content = {
                            "tool_call_id": parsed.get("tool_call_id"),
                            "tool_name": parsed.get("tool_name"),
                            "status": parsed.get("status"),
                            "metadata": {
                                "size_bytes": size_bytes,
                            },
                            "result_ref": parsed.get("result_ref"),
                            # Explicitly indicate no inline result persisted
                            "has_inline_result": False,
                        }
            except Exception:
                slim_content = None

            history = self._project.get_dialog_history(self._dialog_id)
            if slim_content is not None:
                persisted = ToolMessage(
                    content=json.dumps(slim_content, ensure_ascii=False),
                    tool_call_id=slim_content.get("tool_call_id", ""),
                )
                history.add_message(persisted)
            else:
                # Fallback: save original if we cannot minimize (should be rare)
                history.add_message(tool_message)
        except Exception as e:
            agent_logger.error("Failed to append ToolMessage to history", error=str(e))

    def _append_ai_message_with_tool_calls_to_history(self, ai_message: Any) -> None:
        """Append the assistant message that declares tool_calls to history."""
        try:
            if (
                self._project
                and self._dialog_id
                and hasattr(self._project, "get_dialog_history")
            ):
                history = self._project.get_dialog_history(self._dialog_id)
                history.add_message(ai_message)
        except Exception as e:
            agent_logger.error(
                "Failed to append AI tool_calls message to history", error=str(e)
            )

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
                # Check if tool output should be aggregated/persisted
                is_ephemeral = self._is_ephemeral_tool(name)
                if not is_ephemeral:
                    aggregated_tool_results.append({"name": name, "result": result})
                    aggregated_tool_calls.append({"name": name, "args": args})

                # Store result and create reference
                tool_call_id = call.get("id", "") or f"call_{uuid.uuid4().hex[:8]}"

                tool_message, is_ephemeral = await self._build_tool_message(
                    tool_call_id, name, args, result
                )
                # Persist to history only if non-ephemeral and storage path built with reference
                if not is_ephemeral and self._tool_results_storage:
                    self._append_tool_message_to_history(tool_message)

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
                                    text_value = item.get("text")
                                    if isinstance(text_value, str):
                                        parts.append(text_value)
                                    content_value = item.get("content")
                                    if isinstance(content_value, list):
                                        for sub in content_value:
                                            if isinstance(sub, dict):
                                                text_value = sub.get("text")
                                                if isinstance(text_value, str):
                                                    parts.append(text_value)
                            if parts:
                                reasoning_text = "".join(parts)
                        elif isinstance(summary, dict):
                            text_value = summary.get("text")
                            if isinstance(text_value, str):
                                reasoning_text = text_value
                            content_value = summary.get("content")
                            if isinstance(content_value, list):
                                parts2: list[str] = []
                                for sub in content_value:
                                    if isinstance(sub, dict):
                                        text_value = sub.get("text")
                                        if isinstance(text_value, str):
                                            parts2.append(text_value)
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

            # Build tool_calls payload; require provider-supplied IDs
            tool_calls_payload = []
            for tool_call in accumulated_tool_calls:
                name_preview = tool_call.get("name", "")
                try:
                    args_preview = json.loads(tool_call.get("args", "{}") or "{}")
                except Exception:
                    args_preview = {}
                call_id = tool_call.get("id", "")
                if not call_id:
                    # If the provider hasn't supplied an id, skip this call to avoid API mismatch
                    agent_logger.error(
                        "Missing tool_call id in streamed chunks; skipping call",
                        tool_name=name_preview,
                    )
                    continue
                tool_calls_payload.append(
                    {
                        "name": name_preview,
                        "args": args_preview,
                        "id": call_id,
                    }
                )

            # Create AI message with tool_calls set at construction
            ai_message = AIMessage(
                content=accumulated_content or "", tool_calls=tool_calls_payload
            )
            # Ensure tool_calls are also present in additional_kwargs for SQL history round-trip
            try:
                existing_kwargs = dict(
                    getattr(ai_message, "additional_kwargs", {}) or {}
                )
                existing_kwargs["tool_calls"] = tool_calls_payload
                ai_message.additional_kwargs = existing_kwargs
            except Exception:
                pass

            # Append the assistant tool-call message BEFORE tool outputs
            conversation.append(ai_message)
            # Persist AI tool_calls message to history for next turns
            self._append_ai_message_with_tool_calls_to_history(ai_message)

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

                    # Emit tool_call as a structured chunk
                    yield {"type": "tool_call", "name": name, "args": args}

                    # Execute tool
                    result = await self.tool_manager.run_tool(name, **args)
                    is_ephemeral = self._is_ephemeral_tool(name)

                    # Immediately yield file_edit in the same stream if tool produced a file change
                    if isinstance(result, dict) and result.get("type") in {
                        "replace_file_result",
                        "write_file_result",
                        "delete_file_result",
                    }:
                        file_path = result.get("path") or result.get("file")
                        diff = result.get("diff")
                        checkpoint = result.get("checkpoint")
                        if file_path:
                            # Yield file_edit directly in the chunk stream for immediate delivery
                            yield {
                                "type": "file_edit",
                                "file": file_path,
                                "diff": diff,
                                "checkpoint": checkpoint,
                            }

                    # Store result and create reference (tool_id must be present)
                    if not tool_id:
                        raise RuntimeError(
                            "Missing tool_call id; cannot attach tool output"
                        )

                    tool_message, is_ephemeral = await self._build_tool_message(
                        tool_id, name, args, result
                    )
                    if not is_ephemeral and self._tool_results_storage:
                        self._append_tool_message_to_history(tool_message)

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

            # Assistant message already appended above
