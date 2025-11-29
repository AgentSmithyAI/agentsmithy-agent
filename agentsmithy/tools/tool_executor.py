from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.messages.tool import ToolCallChunk

from agentsmithy.dialogs.storages.usage import DialogUsageStorage
from agentsmithy.domain.events import (
    ChatEndEvent,
    ChatEvent,
    ChatStartEvent,
    DoneEvent,
    ErrorEvent,
    FileEditEvent,
    ReasoningEndEvent,
    ReasoningEvent,
    ReasoningStartEvent,
    StreamEvent,
    ToolCallEvent,
)
from agentsmithy.llm.provider import LLMProvider
from agentsmithy.llm.providers.types import (
    AccumulatedToolCall,
    MessageContent,
    NormalizedUsage,
    ToolCallPayload,
    is_text_content_block,
)
from agentsmithy.storage.tool_results import ToolResultsStorage
from agentsmithy.utils.logger import agent_logger

from .core.types import ToolError
from .integration.langchain_adapter import as_langchain_tools
from .registry import ToolRegistry

if TYPE_CHECKING:
    from agentsmithy.core.project import Project


class ToolExecutor:
    """Bridge between LLM tool-calls and concrete tool execution.

    Exposes two paths:
    - process_with_tools(stream=True) -> AsyncGenerator[str|dict]
    - process_with_tools_async(stream=False) -> dict
    """

    # Maximum iterations to prevent infinite loops when model repeatedly makes the same error
    MAX_ITERATIONS = 10

    def __init__(self, tool_manager: ToolRegistry, llm_provider: LLMProvider) -> None:
        self.tool_manager = tool_manager
        self.llm_provider = llm_provider
        # Optional SSE callback to emit structured events upstream if needed
        self._sse_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._project: Project | None = None
        self._dialog_id: str | None = None
        # Set via set_context(...)
        self._tool_results_storage: ToolResultsStorage | None = None

    def dispose(self) -> None:
        """Explicitly clean up resources. Should be called on shutdown."""
        if self._tool_results_storage is not None:
            try:
                self._tool_results_storage.dispose()
                self._tool_results_storage = None
            except Exception:
                pass

    def __del__(self) -> None:
        """Clean up resources on garbage collection (fallback only).

        Note: __del__ is not guaranteed to run during interpreter shutdown.
        Use dispose() for reliable cleanup.
        """
        self.dispose()

    def set_sse_callback(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        self._sse_callback = callback

    def set_context(self, project: Project | None, dialog_id: str | None) -> None:
        """Set project and dialog context for tool results storage."""
        # Dispose old storage before creating new one
        if self._tool_results_storage is not None:
            try:
                self._tool_results_storage.dispose()
            except Exception:
                pass

        self._project = project
        self._dialog_id = dialog_id
        if project and dialog_id:
            self._tool_results_storage = ToolResultsStorage(project, dialog_id)
        else:
            self._tool_results_storage = None

        # Propagate project root to all tools
        if project:
            self.tool_manager.set_project_root(str(project.root))

        # Some tools have their own set_context method (e.g., GetPreviousResultTool)
        for tool in self.tool_manager._tools.values():
            if hasattr(tool, "set_context") and callable(tool.set_context):
                try:
                    tool.set_context(project, dialog_id)
                except Exception:
                    pass

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

    def _extract_usage_from_response(
        self, response: AIMessageChunk | AIMessage
    ) -> dict[str, int] | None:
        """Extract usage/token information from LLM response or chunk.

        Supports multiple provider formats (OpenAI, Anthropic, etc).
        Returns dict with token counts or None if not available.
        """
        # Prefer typed usage_metadata from LangChain (UsageMetadata is a TypedDict)
        usage_metadata: UsageMetadata | None = response.usage_metadata
        if usage_metadata is not None:
            return {
                "input_tokens": usage_metadata["input_tokens"],
                "output_tokens": usage_metadata["output_tokens"],
                "total_tokens": usage_metadata["total_tokens"],
            }

        # Fallback to nested dicts for providers that don't use usage_metadata
        meta = response.response_metadata or {}
        add = response.additional_kwargs or {}

        # Priority order for usage extraction
        candidates: list[dict[str, Any] | None] = [
            (
                meta.get("token_usage")
                if isinstance(meta.get("token_usage"), dict)
                else None
            ),
            add.get("usage") if isinstance(add.get("usage"), dict) else None,
        ]

        for candidate in candidates:
            if candidate:
                return candidate

        return None

    def _normalize_usage_tokens(self, usage: dict[str, int]) -> NormalizedUsage:
        """Normalize token field names across different providers.

        Returns NormalizedUsage with: prompt_tokens, completion_tokens, total_tokens
        """
        # Normalize prompt tokens (OpenAI vs Anthropic naming)
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")

        # Normalize completion tokens
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": usage.get("total_tokens"),
        }

    def _persist_usage(self, usage: dict[str, int] | None) -> None:
        """Persist normalized usage data to storage."""
        if not (self._project and self._dialog_id and usage):
            return

        try:
            normalized = self._normalize_usage_tokens(usage)
            with DialogUsageStorage(self._project, self._dialog_id) as usage_storage:
                usage_storage.upsert(
                    prompt_tokens=normalized["prompt_tokens"],
                    completion_tokens=normalized["completion_tokens"],
                    total_tokens=normalized["total_tokens"],
                    model_name=self.llm_provider.get_model_name(),
                )
        except Exception as e:
            agent_logger.error(
                "Failed to persist usage",
                exc_info=True,
                error=str(e),
                dialog_id=self._dialog_id,
            )

    def _extract_reasoning_from_chunk(self, chunk: AIMessageChunk) -> str | None:
        """Extract reasoning text from a streaming chunk.

        Uses LangChain's content_blocks which normalizes reasoning across providers.
        Returns reasoning text if found, None otherwise.
        """
        # content_blocks normalizes all formats (summary, reasoning_content, etc.)
        # into standard ReasoningContentBlock with 'reasoning' field
        parts: list[str] = []
        for block in chunk.content_blocks:
            if block.get("type") == "reasoning":
                reasoning = block.get("reasoning")
                if isinstance(reasoning, str) and reasoning:
                    parts.append(reasoning)
        return "".join(parts) if parts else None

    def _build_tool_calls_payload(
        self, accumulated_tool_calls: list[AccumulatedToolCall]
    ) -> list[ToolCallPayload]:
        """Convert accumulated tool call chunks into standardized payload.

        Filters out calls without IDs to avoid API mismatches.
        """
        tool_calls_payload: list[ToolCallPayload] = []
        for tool_call in accumulated_tool_calls:
            name = tool_call["name"]
            try:
                args = json.loads(tool_call["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            call_id = tool_call["id"]

            if not call_id:
                agent_logger.error(
                    "Missing tool_call id in streamed chunks; skipping call",
                    tool_name=name,
                )
                continue

            tool_calls_payload.append(
                {
                    "name": name,
                    "args": args,
                    "id": call_id,
                }
            )

        return tool_calls_payload

    def _extract_text_from_content(self, content: MessageContent) -> str | None:
        """Extract text string from various content formats.

        Handles both string content and list-of-dicts formats.
        """
        if isinstance(content, str):
            return content if content else None

        # LangChain may return content as list of dicts for newer models
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and is_text_content_block(item):
                text = item.get("text")
                if text:
                    text_parts.append(text)
        return "".join(text_parts) if text_parts else None

    def _accumulate_tool_call_chunk(
        self,
        tc_chunk: ToolCallChunk,
        current_tool_call: AccumulatedToolCall | None,
        accumulated_tool_calls: list[AccumulatedToolCall],
    ) -> AccumulatedToolCall | None:
        """Process a tool_call_chunk and update accumulation state.

        Returns the updated current_tool_call (or a new one if started).
        """
        chunk_index = tc_chunk.get("index")
        chunk_id = tc_chunk.get("id")
        chunk_name = tc_chunk.get("name")
        chunk_args = tc_chunk.get("args")

        if chunk_index is not None:
            # Check if continuing current tool call
            if current_tool_call and current_tool_call["index"] == chunk_index:
                # Continue accumulating
                if chunk_id and not current_tool_call["id"]:
                    current_tool_call["id"] = chunk_id
                if chunk_name:
                    current_tool_call["name"] += chunk_name
                if chunk_args:
                    current_tool_call["args"] += chunk_args
            else:
                # New tool call - finalize previous one
                if current_tool_call and current_tool_call["name"]:
                    accumulated_tool_calls.append(current_tool_call)
                current_tool_call = {
                    "index": chunk_index,
                    "id": chunk_id or "",
                    "name": chunk_name or "",
                    "args": chunk_args or "",
                }
        elif current_tool_call:
            # Chunks without index - accumulate to current
            if chunk_name:
                current_tool_call["name"] += chunk_name
            if chunk_args:
                current_tool_call["args"] += chunk_args

        return current_tool_call

    async def _build_tool_message(
        self,
        tool_call_id: str,
        name: str,
        args: dict[str, Any],
        result: dict[str, Any] | ToolError,
    ) -> tuple[ToolMessage, bool]:
        """Create a ToolMessage for a tool result, optionally persisting it.

        Returns a tuple of (tool_message, is_ephemeral). When ephemeral, the
        message contains only inline results and no history/storage is written.
        """
        is_ephemeral = self._is_ephemeral_tool(name)

        # Convert ToolError to dict for serialization
        if isinstance(result, ToolError):
            result_dict: dict[str, Any] = result.model_dump()
            is_error = True
        else:
            result_dict = result
            is_error = False

        # If storage is available and tool is not ephemeral, persist and build reference
        if self._tool_results_storage and not is_ephemeral:
            result_ref = await self._tool_results_storage.store_result(
                tool_call_id=tool_call_id,
                tool_name=name,
                args=args,
                result=result_dict,
            )
            metadata = await self._tool_results_storage.get_metadata(tool_call_id)

            inline_result_json = json.dumps(result_dict, ensure_ascii=False)
            content = {
                "tool_call_id": tool_call_id,
                "tool_name": name,
                "status": "error" if is_error else "success",
                "metadata": {
                    "size_bytes": metadata.size_bytes if metadata else 0,
                    "summary": metadata.summary if metadata else "",
                    "truncated_preview": self._tool_results_storage.get_truncated_preview(
                        result_dict
                    ),
                    "result_present": True,
                    "result_length_bytes": len(inline_result_json.encode("utf-8")),
                },
                "result_ref": result_ref.to_dict(),
                "inline_result": result_dict,
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
        inline_result_json = json.dumps(result_dict, ensure_ascii=False)
        content = {
            "tool_call_id": tool_call_id,
            "tool_name": name,
            "status": "error" if is_error else "success",
            "metadata": {
                "size_bytes": len(inline_result_json.encode("utf-8")),
                "summary": "",
                "truncated_preview": None,
                "result_present": True,
                "result_length_bytes": len(inline_result_json.encode("utf-8")),
            },
            "inline_result": result_dict,
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
                # Redact ephemeral tool_calls from the persisted history so the
                # agent won't see ephemeral calls and try to fetch their outputs later.
                tool_calls = list(getattr(ai_message, "tool_calls", []) or [])
                if tool_calls:
                    filtered_calls: list[dict[str, Any]] = []
                    for tc in tool_calls:
                        try:
                            name_value = tc.get("name", "")
                        except Exception:
                            name_value = ""
                        if not self._is_ephemeral_tool(str(name_value)):
                            filtered_calls.append(tc)

                    # Build a shallow copy of the message for persistence
                    from langchain_core.messages import AIMessage

                    persisted = AIMessage(
                        content=getattr(ai_message, "content", ""),
                        tool_calls=filtered_calls,
                    )
                    try:
                        existing_kwargs = dict(
                            getattr(ai_message, "additional_kwargs", {}) or {}
                        )
                        existing_kwargs["tool_calls"] = filtered_calls
                        persisted.additional_kwargs = existing_kwargs
                    except Exception:
                        pass
                else:
                    persisted = ai_message

                history = self._project.get_dialog_history(self._dialog_id)
                history.add_message(persisted)
        except Exception as e:
            agent_logger.error(
                "Failed to append AI tool_calls message to history", error=str(e)
            )

    def process_with_tools(
        self, messages: list[BaseMessage], stream: bool = True
    ) -> AsyncGenerator[StreamEvent]:
        """Streaming path: yield typed event objects suitable for SSE."""
        return self._process_streaming(messages)

    async def process_with_tools_async(
        self, messages: list[BaseMessage]
    ) -> dict[str, Any]:
        """Non-streaming path using iterative tool loop until completion."""
        bound_llm = self._bind_tools()
        conversation: list[BaseMessage] = list(messages)
        aggregated_tool_results: list[dict[str, Any]] = []
        aggregated_tool_calls: list[dict[str, Any]] = []

        # iteration_count: Used only for logging/debugging progress
        # consecutive_errors: Checked to prevent error loops
        #
        # Note: iteration_count is NOT limited - model should work as long as needed
        # for complex tasks. We only limit consecutive_errors to prevent infinite
        # error loops (model repeatedly failing the same way).
        iteration_count = 0
        consecutive_errors = 0

        while True:
            iteration_count += 1
            # Check for too many CONSECUTIVE errors (not total iterations)
            if consecutive_errors >= self.MAX_ITERATIONS:
                raise RuntimeError(
                    f"Maximum consecutive errors ({self.MAX_ITERATIONS}) reached. "
                    "Model is stuck in an error loop."
                )

            agent_logger.info(
                "LLM invoke", messages=len(conversation), iteration=iteration_count
            )
            response = await bound_llm.ainvoke(conversation)

            # Extract and persist usage using helper
            usage = self._extract_usage_from_response(response)
            self._persist_usage(usage)

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

                # Check if tool execution returned an error
                if isinstance(result, ToolError):
                    # Tool failed - increment error counter
                    consecutive_errors += 1
                    agent_logger.error(
                        "Tool execution error (recoverable)",
                        tool_name=name,
                        error_code=result.code,
                        consecutive_errors=consecutive_errors,
                    )
                else:
                    # Tool succeeded - reset error counter
                    consecutive_errors = 0

                # Store result and create reference
                tool_call_id = call.get("id", "") or f"call_{uuid.uuid4().hex[:8]}"

                tool_message, is_ephemeral = await self._build_tool_message(
                    tool_call_id, name, args, result
                )

                # Check if tool output should be aggregated/persisted
                if not is_ephemeral:
                    aggregated_tool_results.append({"name": name, "result": result})
                    aggregated_tool_calls.append({"name": name, "args": args})
                # Persist to history only if non-ephemeral and storage path built with reference
                if not is_ephemeral and self._tool_results_storage:
                    self._append_tool_message_to_history(tool_message)

                conversation.append(tool_message)

    async def _process_streaming(
        self, messages: list[BaseMessage]
    ) -> AsyncGenerator[StreamEvent]:
        """Streaming loop: emit typed event objects as they happen."""
        bound_llm = self._bind_tools()
        conversation: list[BaseMessage] = list(messages)

        # iteration_count: Used only for logging/debugging progress
        # consecutive_errors: Checked to prevent error loops
        #
        # Note: iteration_count is NOT limited - model should work as long as needed
        # for complex tasks. We only limit consecutive_errors to prevent infinite
        # error loops (model repeatedly failing the same way).
        iteration_count = 0
        consecutive_errors = 0

        while True:
            iteration_count += 1
            # Check for too many CONSECUTIVE errors (not total iterations)
            if consecutive_errors >= self.MAX_ITERATIONS:
                error_msg = (
                    f"Maximum consecutive errors ({self.MAX_ITERATIONS}) reached. "
                    "Model is stuck in an error loop."
                )
                agent_logger.error(error_msg, consecutive_errors=consecutive_errors)
                yield ErrorEvent(error=error_msg)
                break

            agent_logger.info(
                "LLM streaming", messages=len(conversation), iteration=iteration_count
            )

            # Use astream for true streaming
            accumulated_content = ""
            accumulated_tool_calls: list[AccumulatedToolCall] = []
            current_tool_call: AccumulatedToolCall | None = None

            # Boundary markers for chat and reasoning
            chat_started = False
            reasoning_started = False

            last_usage: dict[str, int] | None = None
            # Get stream kwargs from provider (vendor-specific)
            stream_kwargs: dict[str, Any] = getattr(
                self.llm_provider, "get_stream_kwargs", lambda: {}
            )()
            stream_iter = bound_llm.astream(conversation, **stream_kwargs)

            try:
                async for chunk in stream_iter:
                    # chunk is AIMessageChunk from LangChain
                    if not isinstance(chunk, AIMessageChunk):
                        continue

                    # Capture usage tokens using helper
                    usage = self._extract_usage_from_response(chunk)
                    if usage:
                        last_usage = usage

                    # Extract and yield reasoning if present
                    reasoning_text = self._extract_reasoning_from_chunk(chunk)
                    if reasoning_text:
                        if not reasoning_started:
                            reasoning_started = True
                            yield ReasoningStartEvent()
                        yield ReasoningEvent(content=reasoning_text)

                    # Handle content chunks
                    content = chunk.content
                    if content:
                        text = self._extract_text_from_content(content)
                        if text:
                            if not chat_started:
                                chat_started = True
                                yield ChatStartEvent()
                            accumulated_content += text
                            yield ChatEvent(content=text)

                    # Handle tool call chunks
                    tool_call_chunks: list[ToolCallChunk] = chunk.tool_call_chunks
                    for tc_chunk in tool_call_chunks:
                        current_tool_call = self._accumulate_tool_call_chunk(
                            tc_chunk, current_tool_call, accumulated_tool_calls
                        )

                # Close boundary markers at the end of this streaming chunk
                if reasoning_started:
                    yield ReasoningEndEvent()
                if chat_started and accumulated_content:
                    yield ChatEndEvent()

                # Add the last tool call if exists
                if current_tool_call and current_tool_call["name"]:
                    accumulated_tool_calls.append(current_tool_call)

            except Exception as stream_error:
                # LLM streaming failed (e.g., context window exceeded)
                agent_logger.error(
                    "LLM streaming failed",
                    exc_info=True,
                    error=str(stream_error),
                )
                # Close any open boundaries
                if reasoning_started:
                    yield ReasoningEndEvent()
                if chat_started:
                    yield ChatEndEvent()
                # Yield error event to client
                yield ErrorEvent(error=f"LLM error: {str(stream_error)}")
                # Yield DONE event to signal end of stream
                # (chat_service doesn't know stream ended early without this)
                yield DoneEvent()
                return  # Stop processing

            # If no tool calls, we're done - model finished successfully
            if not accumulated_tool_calls:
                # Persist usage using helper
                self._persist_usage(last_usage or {})
                # Stream might have already yielded all content chunks
                # Model succeeded (no need to reset error counter - exiting loop)
                break

            # Create AI message with tool calls for conversation history
            from langchain_core.messages import AIMessage

            # Build tool_calls payload using helper
            tool_calls_payload = self._build_tool_calls_payload(accumulated_tool_calls)

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
                    name = tool_call["name"]
                    tool_id = tool_call["id"]
                    args_str = tool_call["args"] or "{}"

                    args = json.loads(args_str)

                    if not name:
                        continue

                    # Emit tool_call as a structured event
                    yield ToolCallEvent(name=name, args=args)

                    # Execute tool (tool_manager handles all tool exceptions centrally)
                    result = await self.tool_manager.run_tool(name, **args)

                    # Check if tool execution returned an error
                    # tool_manager.run_tool() catches all exceptions and returns ToolError
                    if isinstance(result, ToolError):
                        # Tool failed - this is recoverable, model can retry with different approach
                        # Do NOT send to SSE (not terminal), only log and add to conversation
                        consecutive_errors += 1  # Increment error counter
                        agent_logger.error(
                            "Tool execution error (recoverable)",
                            tool_name=name,
                            error_code=result.code,
                            error_type=result.error_type,
                            consecutive_errors=consecutive_errors,
                        )

                        # Build tool message with error result so model can see it
                        if not tool_id:
                            raise RuntimeError(
                                "Missing tool_call id; cannot attach tool output"
                            )

                        tool_message, is_ephemeral = await self._build_tool_message(
                            tool_id, name, args, result
                        )
                        if not is_ephemeral and self._tool_results_storage:
                            self._append_tool_message_to_history(tool_message)

                        # Add error to conversation so model can retry
                        conversation.append(tool_message)

                        # Continue processing next tool call
                        continue

                    # Tool succeeded - reset error counter
                    consecutive_errors = 0

                    # Handle file edits and other results
                    # Immediately yield file_edit in the same stream if tool produced a file change
                    if isinstance(result, dict) and result.get("type") in {
                        "replace_file_result",
                        "write_file_result",
                        "delete_file_result",
                    }:
                        file_path = result.get("path") or result.get("file")
                        diff = result.get("diff")
                        if file_path:
                            # Yield file_edit directly in the chunk stream for immediate delivery
                            yield FileEditEvent(file=file_path, diff=diff)

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
                    # Tool argument parsing failed - this is recoverable, model can retry with correct JSON
                    # Do NOT send to SSE (not terminal), only log and add to conversation
                    consecutive_errors += 1  # Increment error counter
                    agent_logger.error(
                        "Tool argument parse error (recoverable)",
                        tool_name=name,
                        args_str=args_str,
                        consecutive_errors=consecutive_errors,
                    )

                    # Create error result to send back to model
                    error_result = ToolError(
                        name=name,
                        code="args_parse_failed",
                        error=f"Failed to parse tool arguments: {str(e)}",
                        error_type="JSONDecodeError",
                    )

                    # Build tool message with error result
                    tool_message, is_ephemeral = await self._build_tool_message(
                        tool_id, name, {}, error_result
                    )
                    if not is_ephemeral and self._tool_results_storage:
                        self._append_tool_message_to_history(tool_message)

                    # Add error to conversation so model can retry
                    conversation.append(tool_message)

                    # Continue processing (don't return) - model may retry
                    continue

                except Exception as e:
                    # Unexpected error during tool result processing (not tool execution itself)
                    # Tool execution errors are handled centrally by tool_manager and checked above
                    # This catches errors in _build_tool_message, storage, etc.
                    # If we can continue - it's recoverable, if not - it's terminal
                    consecutive_errors += 1  # Increment error counter
                    agent_logger.error(
                        "Unexpected error in tool result processing (recoverable)",
                        tool_name=name,
                        error=str(e),
                        error_type=type(e).__name__,
                        consecutive_errors=consecutive_errors,
                    )

                    # Do NOT send to SSE (not terminal), only log and try to add to conversation
                    # Create error result to send back to model
                    error_result = ToolError(
                        name=name,
                        code="processing_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                    # Try to build tool message with error result
                    try:
                        tool_message, is_ephemeral = await self._build_tool_message(
                            tool_id, name, {}, error_result
                        )
                        if not is_ephemeral and self._tool_results_storage:
                            self._append_tool_message_to_history(tool_message)
                        conversation.append(tool_message)
                    except Exception:
                        # If even error message creation fails, just log and continue
                        agent_logger.error("Failed to create error tool message")

                    # Continue processing (don't return) - model may retry
                    continue

            # Assistant message already appended above
