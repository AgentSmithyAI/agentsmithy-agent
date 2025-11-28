from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, TypedDict, TypeGuard

from langchain_core.messages import BaseMessage, ToolMessage

from agentsmithy.dialogs.storages.usage import DialogUsageStorage
from agentsmithy.domain.events import EventType
from agentsmithy.llm.provider import LLMProvider
from agentsmithy.storage.tool_results import ToolResultsStorage
from agentsmithy.utils.logger import agent_logger

from .integration.langchain_adapter import as_langchain_tools
from .registry import ToolRegistry

if TYPE_CHECKING:
    from agentsmithy.core.project import Project


# --- Reasoning content block types (LangChain Responses API format) ---
# These match what langchain-openai actually returns, not langchain-core's
# ReasoningContentBlock which is incomplete.


class SummaryTextItem(TypedDict, total=False):
    """Single summary text item in reasoning block."""

    index: int
    type: Literal["summary_text"]
    text: str


class ReasoningBlock(TypedDict, total=False):
    """Reasoning content block as returned by LangChain for Responses API.

    LangChain-OpenAI returns reasoning in two possible formats:
    1. Legacy: {"type": "reasoning", "reasoning": "..."}
    2. Responses API v1: {"type": "reasoning", "summary": [...]}
    """

    type: Literal["reasoning"]
    reasoning: str  # Legacy format
    text: str  # Alternative legacy format
    summary: list[SummaryTextItem]  # Responses API v1 format
    index: int
    id: str


def is_reasoning_block(block: dict[str, Any]) -> TypeGuard[ReasoningBlock]:
    """Type guard to check if a dict is a ReasoningBlock."""
    return block.get("type") == "reasoning"


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

    def _extract_usage_from_response(self, response: Any) -> dict[str, Any]:
        """Extract usage/token information from LLM response or chunk.

        Supports multiple provider formats (OpenAI, Anthropic, etc).
        """
        # Try multiple paths to find usage data
        meta = getattr(response, "response_metadata", {}) or {}
        add = getattr(response, "additional_kwargs", {}) or {}

        # Priority order for usage extraction
        candidates = [
            self._get_nested(meta, "token_usage"),
            self._get_nested(add, "usage"),
            getattr(response, "usage_metadata", None),
            self._get_nested(meta, "finish_reason_data", "usage"),
            self._get_nested(meta, "model_kwargs", "usage"),
        ]

        # Return first valid dict
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate:
                return candidate

        # Check direct usage attribute (may be object)
        if hasattr(response, "usage"):
            direct_usage = getattr(response, "usage", None)
            if direct_usage:
                if hasattr(direct_usage, "__dict__"):
                    return direct_usage.__dict__
                elif hasattr(direct_usage, "dict") and callable(direct_usage.dict):
                    return direct_usage.dict()
                elif isinstance(direct_usage, dict):
                    return direct_usage

        return {}

    def _normalize_usage_tokens(self, usage: dict[str, Any]) -> dict[str, Any]:
        """Normalize token field names across different providers.

        Returns dict with: prompt_tokens, completion_tokens, total_tokens
        """
        # Normalize prompt tokens (OpenAI vs Anthropic naming)
        prompt_tokens = usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = usage.get("input_tokens")

        # Normalize completion tokens
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = usage.get("output_tokens")

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": usage.get("total_tokens"),
        }

    def _persist_usage(self, usage: dict[str, Any]) -> None:
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

    def _extract_reasoning_from_chunk(self, chunk: Any) -> str | None:
        """Extract reasoning text from a streaming chunk.

        Handles multiple provider formats (OpenAI o1/gpt-5, etc).
        Returns reasoning text if found, None otherwise.
        """
        try:
            # 1) Direct attribute exposed by some adapters (e.g., OpenAI o1/gpt-5)
            reasoning_content = getattr(chunk, "reasoning_content", None)
            if isinstance(reasoning_content, str) and reasoning_content:
                return reasoning_content

            # 2) Nested fields in additional_kwargs/response_metadata
            add = getattr(chunk, "additional_kwargs", {}) or {}
            meta = getattr(chunk, "response_metadata", {}) or {}

            reasoning = self._get_nested(add, "reasoning") or self._get_nested(
                meta, "reasoning"
            )

            if isinstance(reasoning, str) and reasoning:
                return reasoning
            if isinstance(reasoning, dict):
                parsed = self._parse_reasoning_dict(reasoning)
                if parsed:
                    return parsed

            # 3) Reasoning blocks inside content list (LangChain content blocks API)
            #    Newer OpenAI models (gpt-5 family) stream content as a list of blocks.
            #    See ReasoningBlock TypedDict for expected structure.
            content = getattr(chunk, "content", None)
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and is_reasoning_block(item):
                        text = self._extract_text_from_reasoning_block(item)
                        if text:
                            parts.append(text)
                if parts:
                    return "".join(parts)

            return None
        except Exception:
            return None

    def _extract_text_from_reasoning_block(self, block: ReasoningBlock) -> str | None:
        """Extract text from a reasoning content block.

        Handles both legacy format (reasoning/text fields) and
        Responses API v1 format (summary list).

        Args:
            block: A ReasoningBlock (validated by is_reasoning_block TypeGuard)

        Returns:
            Extracted text or None
        """
        # Legacy format: direct reasoning or text field
        text = block.get("reasoning") or block.get("text")
        if text:
            return text

        # Responses API v1 format: summary is a list of SummaryTextItem
        summary = block.get("summary")
        if summary is not None:
            texts: list[str] = []
            for item in summary:
                # item is already typed as SummaryTextItem from ReasoningBlock
                t = item.get("text")
                if t:
                    texts.append(t)
            if texts:
                return "".join(texts)

        return None

    def _get_nested(self, obj: Any, *keys: str, default: Any = None) -> Any:
        """Safely access nested dict keys (like Optional chaining in JS).

        Example: _get_nested(data, "response", "metadata", "usage")
        Returns value or default if any key is missing.
        """
        current = obj
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current

    def _extract_text_recursive(self, obj: Any) -> list[str]:
        """Recursively extract all text values from nested dict/list structure.

        Traverses obj and collects all string values from 'text' keys.
        Works like a lens/traversal in functional programming.
        """
        if isinstance(obj, str):
            return [obj]
        elif isinstance(obj, dict):
            texts = []
            # Check direct text field
            if "text" in obj and isinstance(obj["text"], str):
                texts.append(obj["text"])
            # Recurse into content field
            if "content" in obj:
                texts.extend(self._extract_text_recursive(obj["content"]))
            return texts
        elif isinstance(obj, list):
            # Flatten all texts from list items
            return [text for item in obj for text in self._extract_text_recursive(item)]
        else:
            return []

    def _parse_reasoning_dict(self, reasoning: dict) -> str | None:
        """Parse reasoning from dict structure (nested content/text fields)."""
        # Try summary field first
        summary = reasoning.get("summary")

        if isinstance(summary, str):
            return summary

        # Extract all text recursively from summary
        if summary is not None:
            texts = self._extract_text_recursive(summary)
            if texts:
                return "".join(texts)

        # Fallback to content field
        if isinstance(reasoning.get("content"), str):
            return reasoning.get("content")

        return None

    def _build_tool_calls_payload(
        self, accumulated_tool_calls: list[dict]
    ) -> list[dict[str, Any]]:
        """Convert accumulated tool call chunks into standardized payload.

        Filters out calls without IDs to avoid API mismatches.
        """
        tool_calls_payload = []
        for tool_call in accumulated_tool_calls:
            name = tool_call.get("name", "")
            try:
                args = json.loads(tool_call.get("args", "{}") or "{}")
            except Exception:
                args = {}
            call_id = tool_call.get("id", "")

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

    def _extract_text_from_content(self, content: Any) -> str | None:
        """Extract text string from various content formats.

        Handles both string content and list-of-dicts formats.
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # LangChain may return content as list of dicts for newer models
            text_parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            if text_parts:
                return "".join(text_parts)
        return None

    def _accumulate_tool_call_chunk(
        self,
        tc_chunk: dict,
        current_tool_call: dict | None,
        accumulated_tool_calls: list[dict],
    ) -> dict | None:
        """Process a tool_call_chunk and update accumulation state.

        Returns the updated current_tool_call (or a new one if started).
        """
        chunk_index = tc_chunk.get("index")

        if chunk_index is not None:
            # Check if continuing current tool call
            if current_tool_call and current_tool_call.get("index") == chunk_index:
                # Continue accumulating
                if tc_chunk.get("id") and not current_tool_call.get("id"):
                    current_tool_call["id"] = tc_chunk["id"]
                if tc_chunk.get("name"):
                    current_tool_call["name"] += tc_chunk["name"]
                if tc_chunk.get("args"):
                    current_tool_call["args"] += tc_chunk["args"]
            else:
                # New tool call - finalize previous one
                if current_tool_call and "name" in current_tool_call:
                    accumulated_tool_calls.append(current_tool_call)
                current_tool_call = {
                    "index": chunk_index,
                    "id": tc_chunk.get("id", ""),
                    "name": tc_chunk.get("name", ""),
                    "args": tc_chunk.get("args", ""),
                }
        elif current_tool_call:
            # Chunks without index - accumulate to current
            if tc_chunk.get("name"):
                current_tool_call["name"] += tc_chunk["name"]
            if tc_chunk.get("args"):
                current_tool_call["args"] += tc_chunk["args"]

        return current_tool_call

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
                    "error"
                    if isinstance(result, dict)
                    and isinstance(result.get("type"), str)
                    and ("error" in result["type"] or result["type"] == "tool_error")
                    else "success"
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
            "status": (
                "error"
                if isinstance(result, dict)
                and isinstance(result.get("type"), str)
                and ("error" in result["type"] or result["type"] == "tool_error")
                else "success"
            ),
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
    ) -> AsyncGenerator[Any]:
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
                if isinstance(result, dict) and result.get("type") == "tool_error":
                    # Tool failed - increment error counter
                    consecutive_errors += 1
                    agent_logger.error(
                        "Tool execution error (recoverable)",
                        tool_name=name,
                        error_code=result.get("code"),
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
    ) -> AsyncGenerator[Any]:
        """Streaming loop: emit content chunks and tool results as they happen."""
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
                yield {"type": EventType.ERROR.value, "error": error_msg}
                break

            agent_logger.info(
                "LLM streaming", messages=len(conversation), iteration=iteration_count
            )

            # Use astream for true streaming
            accumulated_content = ""
            accumulated_tool_calls: list[dict] = []
            current_tool_call: dict | None = None

            # Boundary markers for chat and reasoning
            chat_started = False
            reasoning_started = False

            last_usage: dict[str, Any] | None = None
            # Get stream kwargs from provider (vendor-specific)
            stream_kwargs: dict[str, Any] = getattr(
                self.llm_provider, "get_stream_kwargs", lambda: {}
            )()
            stream_iter = bound_llm.astream(conversation, **stream_kwargs)

            try:
                async for chunk in stream_iter:
                    # Capture usage tokens using helper
                    usage = self._extract_usage_from_response(chunk)
                    if usage:
                        last_usage = usage

                    # Extract and yield reasoning if present
                    reasoning_text = self._extract_reasoning_from_chunk(chunk)
                    if reasoning_text:
                        if not reasoning_started:
                            reasoning_started = True
                            yield {"type": EventType.REASONING_START.value}
                        yield {
                            "type": EventType.REASONING.value,
                            "content": reasoning_text,
                        }

                    # Handle content chunks
                    content = getattr(chunk, "content", None)
                    if content:
                        text = self._extract_text_from_content(content)
                        if text:
                            if not chat_started:
                                chat_started = True
                                yield {"type": "chat_start"}
                            accumulated_content += text
                            yield {"type": EventType.CHAT.value, "content": text}

                    # Handle tool call chunks
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                    for tc_chunk in tool_call_chunks:
                        current_tool_call = self._accumulate_tool_call_chunk(
                            tc_chunk, current_tool_call, accumulated_tool_calls
                        )

                # Close boundary markers at the end of this streaming chunk
                if reasoning_started:
                    yield {"type": EventType.REASONING_END.value}
                if chat_started and accumulated_content:
                    yield {"type": EventType.CHAT_END.value}

                # Add the last tool call if exists
                if (
                    current_tool_call
                    and "name" in current_tool_call
                    and current_tool_call["name"]
                ):
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
                    yield {"type": EventType.REASONING_END.value}
                if chat_started:
                    yield {"type": EventType.CHAT_END.value}
                # Yield error event to client
                yield {
                    "type": EventType.ERROR.value,
                    "error": f"LLM error: {str(stream_error)}",
                }
                # Yield DONE event to signal end of stream
                # (chat_service doesn't know stream ended early without this)
                yield {"type": EventType.DONE.value}
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
                    yield {
                        "type": EventType.TOOL_CALL.value,
                        "name": name,
                        "args": args,
                    }

                    # Execute tool (tool_manager handles all tool exceptions centrally)
                    result = await self.tool_manager.run_tool(name, **args)

                    # Check if tool execution returned an error
                    # tool_manager.run_tool() catches all exceptions and returns {"type": "tool_error"}
                    if isinstance(result, dict) and result.get("type") == "tool_error":
                        # Tool failed - this is recoverable, model can retry with different approach
                        # Do NOT send to SSE (not terminal), only log and add to conversation
                        consecutive_errors += 1  # Increment error counter
                        agent_logger.error(
                            "Tool execution error (recoverable)",
                            tool_name=name,
                            error_code=result.get("code"),
                            error_type=result.get("error_type"),
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
                            yield {
                                "type": EventType.FILE_EDIT.value,
                                "file": file_path,
                                "diff": diff,
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
                    error_result = {
                        "type": "tool_error",
                        "name": name,
                        "code": "args_parse_failed",
                        "error": f"Failed to parse tool arguments: {str(e)}",
                        "error_type": "JSONDecodeError",
                    }

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
                    error_result = {
                        "type": "tool_error",
                        "name": name,
                        "code": "processing_failed",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }

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
