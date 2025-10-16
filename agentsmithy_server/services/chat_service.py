"""Chat service: orchestrates agent processing and yields domain events.

This service centralizes streaming/non-streaming chat logic so routers remain thin.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory
from agentsmithy_server.dialogs.storages.file_edits import DialogFileEditStorage
from agentsmithy_server.dialogs.storages.reasoning import DialogReasoningStorage
from agentsmithy_server.dialogs.storages.summaries import DialogSummaryStorage
from agentsmithy_server.dialogs.summarization.strategy import KEEP_LAST_MESSAGES
from agentsmithy_server.domain.events import EventType
from agentsmithy_server.llm.orchestration.agent_graph import AgentOrchestrator
from agentsmithy_server.utils.logger import api_logger, stream_log


class StreamAbortError(Exception):
    """Signal to abort streaming due to error."""


class ChatService:
    def __init__(self) -> None:
        self._orchestrator: AgentOrchestrator | None = None
        self._active_streams: set[asyncio.Task] = set()
        self._shutdown_event: asyncio.Event | None = None

    def _flush_assistant_buffer(
        self,
        project_dialog: tuple[Any, str] | None,
        dialog_id: str | None,
        assistant_buffer: list[str],
        clear_buffer: bool = False,
    ) -> None:
        """Persist accumulated assistant text to dialog history (best-effort).

        Args:
            project_dialog: Tuple of (project, dialog_id) for history access
            dialog_id: Target dialog ID
            assistant_buffer: Buffer containing accumulated assistant text
            clear_buffer: If True, clear the buffer after flushing (for incremental saves)
        """
        try:
            if assistant_buffer and project_dialog:
                project_obj, pdialog_id = project_dialog
                target_dialog_id = dialog_id or pdialog_id
                if target_dialog_id and hasattr(project_obj, "get_dialog_history"):
                    history = project_obj.get_dialog_history(target_dialog_id)
                    content = "".join(assistant_buffer)
                    if content:
                        history.add_ai_message(content)
                        if clear_buffer:
                            assistant_buffer.clear()
                            api_logger.debug(
                                "Incrementally saved assistant chunk",
                                dialog_id=target_dialog_id,
                                length=len(content),
                            )
        except Exception as e:
            api_logger.error(
                "Failed to append assistant message (stream)",
                exc_info=True,
                error=str(e),
            )

    def _flush_reasoning_buffer(
        self,
        project_dialog: tuple[Any, str] | None,
        dialog_id: str | None,
        reasoning_buffer: list[str],
        clear_buffer: bool = False,
    ) -> int | None:
        """Persist accumulated reasoning text to separate storage (best-effort).

        Args:
            project_dialog: Tuple of (project, dialog_id) for storage access
            dialog_id: Target dialog ID
            reasoning_buffer: Buffer containing accumulated reasoning text
            clear_buffer: If True, clear the buffer after flushing

        Returns:
            ID of saved reasoning block, or None on error
        """
        try:
            if reasoning_buffer and project_dialog:
                project_obj, pdialog_id = project_dialog
                target_dialog_id = dialog_id or pdialog_id
                if target_dialog_id:
                    content = "".join(reasoning_buffer)
                    if content.strip():
                        # Get current message count to link reasoning to next message
                        message_index = -1
                        try:
                            if hasattr(project_obj, "get_dialog_history"):
                                history = project_obj.get_dialog_history(
                                    target_dialog_id
                                )
                                messages = history.get_messages()
                                # Link to the last message (or next message index)
                                message_index = len(messages)
                        except Exception:
                            pass

                        with DialogReasoningStorage(
                            project_obj, target_dialog_id
                        ) as storage:
                            reasoning_id = storage.save(
                                content=content, message_index=message_index
                            )
                            if reasoning_id and clear_buffer:
                                reasoning_buffer.clear()
                                api_logger.debug(
                                    "Saved reasoning block",
                                    dialog_id=target_dialog_id,
                                    reasoning_id=reasoning_id,
                                    length=len(content),
                                    message_index=message_index,
                                )
                            return reasoning_id
        except Exception as e:
            api_logger.error(
                "Failed to save reasoning block (stream)",
                exc_info=True,
                error=str(e),
            )
        return None

    def _get_orchestrator(self) -> AgentOrchestrator:
        if self._orchestrator is None:
            # Orchestrator now supports DI; keep default provider for backwards compatibility
            self._orchestrator = AgentOrchestrator()
        return self._orchestrator

    def invalidate_orchestrator(self) -> None:
        """Invalidate cached orchestrator to force recreation with fresh config."""
        api_logger.info("Invalidating orchestrator cache")
        self._orchestrator = None

    def set_shutdown_event(self, event: asyncio.Event) -> None:
        """Set the shutdown event for graceful termination."""
        self._shutdown_event = event

    async def shutdown(self) -> None:
        """Cancel all active streams during shutdown."""
        api_logger.info("Cancelling active streams", count=len(self._active_streams))
        for task in self._active_streams:
            if not task.done():
                task.cancel()
        # Wait for all tasks to complete
        if self._active_streams:
            await asyncio.gather(*self._active_streams, return_exceptions=True)

    async def _process_structured_chunk(
        self,
        chunk: Any,
        dialog_id: str | None,
        assistant_buffer: list[str],
        project_dialog: tuple[Any, str] | None = None,
        reasoning_buffer: list[str] | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        if isinstance(chunk, dict) and chunk.get("type") in {
            EventType.FILE_EDIT.value,
            EventType.TOOL_CALL.value,
            EventType.ERROR.value,
            EventType.CHAT.value,
            EventType.REASONING.value,
            EventType.CHAT_START.value,
            EventType.CHAT_END.value,
            EventType.REASONING_START.value,
            EventType.REASONING_END.value,
            EventType.SUMMARY_START.value,
            EventType.SUMMARY_END.value,
        }:
            if chunk["type"] == EventType.CHAT.value:
                content = chunk.get("content", "")
                if content:
                    assistant_buffer.append(content)
                    yield SSEEventFactory.chat(
                        content=content, dialog_id=dialog_id
                    ).to_sse()
            elif chunk["type"] == EventType.REASONING.value:
                content = chunk.get("content", "")
                if content:
                    # Accumulate reasoning in buffer for separate storage
                    if reasoning_buffer is not None:
                        reasoning_buffer.append(content)
                    yield SSEEventFactory.reasoning(
                        content=content, dialog_id=dialog_id
                    ).to_sse()
            elif chunk["type"] == EventType.CHAT_START.value:
                yield SSEEventFactory.chat_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.CHAT_END.value:
                # Don't flush here - tool_executor will save complete message with tool_calls
                # If no tool_calls, will be saved by final flush at end of stream
                yield SSEEventFactory.chat_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.REASONING_START.value:
                yield SSEEventFactory.reasoning_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.REASONING_END.value:
                # Save accumulated reasoning to separate storage after reasoning block ends
                if reasoning_buffer is not None:
                    self._flush_reasoning_buffer(
                        project_dialog, dialog_id, reasoning_buffer, clear_buffer=True
                    )
                yield SSEEventFactory.reasoning_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.SUMMARY_START.value:
                yield SSEEventFactory.summary_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.SUMMARY_END.value:
                yield SSEEventFactory.summary_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == EventType.FILE_EDIT.value:
                # Save file edit event to separate storage
                if project_dialog:
                    project_obj, pdialog_id = project_dialog
                    target_dialog_id = dialog_id or pdialog_id
                    if target_dialog_id:
                        try:
                            # Get current message index
                            message_index = -1
                            if hasattr(project_obj, "get_dialog_history"):
                                history = project_obj.get_dialog_history(
                                    target_dialog_id
                                )
                                messages = history.get_messages()
                                message_index = len(messages)

                            with DialogFileEditStorage(
                                project_obj, target_dialog_id
                            ) as storage:
                                storage.save(
                                    file=chunk.get("file", ""),
                                    diff=chunk.get("diff"),
                                    checkpoint=chunk.get("checkpoint"),
                                    message_index=message_index,
                                )
                        except Exception as e:
                            api_logger.error(
                                "Failed to save file edit event",
                                exc_info=True,
                                error=str(e),
                            )

                yield SSEEventFactory.file_edit(
                    file=chunk.get("file", ""),
                    diff=chunk.get("diff"),
                    checkpoint=chunk.get("checkpoint"),
                    dialog_id=dialog_id,
                ).to_sse()
            elif chunk["type"] == EventType.TOOL_CALL.value:
                yield SSEEventFactory.tool_call(
                    name=chunk.get("name", ""),
                    args=chunk.get("args", {}),
                    dialog_id=dialog_id,
                ).to_sse()
            else:
                # Emit error and signal abort
                yield SSEEventFactory.error(
                    message=chunk.get("error", ""), dialog_id=dialog_id
                ).to_sse()
                raise StreamAbortError()
        elif isinstance(chunk, str):
            assistant_buffer.append(chunk)
            yield SSEEventFactory.chat(content=chunk, dialog_id=dialog_id).to_sse()
        else:
            content = str(chunk)
            assistant_buffer.append(content)
            yield SSEEventFactory.chat(content=content, dialog_id=dialog_id).to_sse()

    async def _drain_tool_events_queue(
        self, queue: asyncio.Queue[dict[str, Any]], dialog_id: str | None
    ) -> list[dict[str, str]]:
        """Drain tool events reliably, tolerating race with queue.empty().

        Uses a small timeout loop to catch events that arrive just after the check.
        """
        sse_events: list[dict[str, str]] = []
        # Attempt to pull multiple events with short timeouts
        while True:
            try:
                tool_event = await asyncio.wait_for(queue.get(), timeout=0.05)
            except TimeoutError:
                break
            else:
                # Process the event only if we successfully got one
                if tool_event.get("type") == EventType.TOOL_CALL.value:
                    sse = SSEEventFactory.tool_call(
                        name=tool_event.get("name", ""),
                        args=tool_event.get("args", {}),
                        dialog_id=dialog_id,
                    ).to_sse()
                elif tool_event.get("type") == EventType.FILE_EDIT.value:
                    sse = SSEEventFactory.file_edit(
                        file=tool_event.get("file", ""),
                        diff=tool_event.get("diff"),
                        checkpoint=tool_event.get("checkpoint"),
                        dialog_id=dialog_id,
                    ).to_sse()
                elif tool_event.get("type") == "error":
                    sse = SSEEventFactory.error(
                        message=tool_event.get("error", ""), dialog_id=dialog_id
                    ).to_sse()
                else:
                    sse = SSEEventFactory.chat(
                        content=str(tool_event), dialog_id=dialog_id
                    ).to_sse()
                stream_log(api_logger, "tool_event", None)
                sse_events.append(sse)

        return sse_events

    def _append_user_and_prepare_context(
        self,
        query: str,
        context: dict[str, Any] | None,
        dialog_id: str | None,
        project: Any | None,
    ) -> dict[str, Any]:
        """Append user message and enrich context with dialog history (with summary support)."""
        ctx: dict[str, Any] = dict(context or {})
        if not project or not dialog_id:
            return ctx

        try:
            history = project.get_dialog_history(dialog_id)
            history.add_user_message(query)
        except Exception as e:
            api_logger.error(
                "Failed to append user message", exc_info=True, error=str(e)
            )

        # Load history; use persisted summary when present
        messages = []
        summary_text = None
        try:
            # Try persisted summary to decide whether to load only tail K
            try:
                with DialogSummaryStorage(project, dialog_id) as storage:
                    stored = storage.load()
            except Exception:
                stored = None

            if stored:
                tail_k = KEEP_LAST_MESSAGES
                messages = history.get_messages(limit=tail_k)
                summary_text = stored.summary_text
                api_logger.info(
                    "Context prepared with persisted summary",
                    dialog_id=dialog_id,
                    tail_k=tail_k,
                    summarized_count=stored.summarized_count,
                )
            else:
                messages = history.get_messages()
        except Exception as e:
            api_logger.error(
                "Failed to load dialog history", exc_info=True, error=str(e)
            )

        ctx["dialog"] = {"id": dialog_id, "messages": messages}
        if summary_text:
            ctx["dialog_summary"] = summary_text
        # Add project reference for tool results storage
        ctx["project"] = project
        return ctx

    async def stream_chat(
        self,
        query: str,
        context: dict[str, Any],
        dialog_id: str | None,
        project_dialog: tuple[Any, str] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        api_logger.info("Starting SSE event generation", query=query[:100])

        # Create a task for tracking
        current_task = asyncio.current_task()
        if current_task:
            self._active_streams.add(current_task)

        sse_events_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def sse_callback(event_data: dict[str, Any]):
            await sse_events_queue.put(event_data)

        orchestrator = self._get_orchestrator()
        if hasattr(orchestrator, "set_sse_callback"):
            orchestrator.set_sse_callback(sse_callback)

        try:
            api_logger.debug("Processing request with orchestrator", streaming=True)
            # Centralize history: append user and inject dialog messages into context
            if project_dialog:
                project_obj, pdialog_id = project_dialog
                context = self._append_user_and_prepare_context(
                    query, context, dialog_id or pdialog_id, project_obj
                )
            result = await orchestrator.process_request(
                query=query, context=context, stream=True
            )
            graph_execution = result["graph_execution"]
            api_logger.debug("Graph execution started")

            event_count = 0
            assistant_buffer: list[str] = []
            reasoning_buffer: list[str] = []

            async for state in graph_execution:
                # Check for shutdown signal
                if self._shutdown_event and self._shutdown_event.is_set():
                    api_logger.info("Shutdown detected, terminating stream")
                    # Flush any accumulated assistant content before exit
                    self._flush_assistant_buffer(
                        project_dialog, dialog_id, assistant_buffer
                    )
                    yield SSEEventFactory.error(
                        message="Server is shutting down", dialog_id=dialog_id
                    ).to_sse()
                    yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                    return
                event_count += 1
                api_logger.debug(
                    f"Processing state #{event_count}", state_keys=list(state.keys())
                )

                if state.get("response"):
                    api_logger.debug(
                        "Processing response",
                        has_aiter=hasattr(state["response"], "__aiter__"),
                    )

                    if hasattr(state["response"], "__aiter__"):
                        chunk_count = 0
                        async for chunk in state["response"]:
                            chunk_count += 1
                            try:
                                async for sse_event in self._process_structured_chunk(
                                    chunk,
                                    dialog_id,
                                    assistant_buffer,
                                    project_dialog,
                                    reasoning_buffer,
                                ):
                                    yield sse_event
                                stream_log(
                                    api_logger,
                                    "processed_chunk",
                                    None,
                                    chunk_number=chunk_count,
                                )
                            except StreamAbortError:
                                # Flush buffer before terminating
                                self._flush_assistant_buffer(
                                    project_dialog, dialog_id, assistant_buffer
                                )
                                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                                return
                        # Usage persisted inside ToolExecutor now; nothing to do here
                        api_logger.info(f"Finished streaming {chunk_count} chunks")
                    else:
                        try:
                            async for sse_event in self._process_structured_chunk(
                                state["response"],
                                dialog_id,
                                assistant_buffer,
                                project_dialog,
                                reasoning_buffer,
                            ):
                                yield sse_event
                        except StreamAbortError:
                            # Flush buffer before terminating
                            self._flush_assistant_buffer(
                                project_dialog, dialog_id, assistant_buffer
                            )
                            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                            return

                for key in state.keys():
                    if key.endswith("_agent") and state[key] and key != "response":
                        agent_data = state[key]
                        if isinstance(agent_data, dict) and "response" in agent_data:
                            response = agent_data["response"]

                            if hasattr(response, "__aiter__"):
                                chunk_count = 0
                                async for chunk in response:
                                    chunk_count += 1
                                    try:
                                        async for (
                                            sse_event
                                        ) in self._process_structured_chunk(
                                            chunk,
                                            dialog_id,
                                            assistant_buffer,
                                            project_dialog,
                                            reasoning_buffer,
                                        ):
                                            yield sse_event
                                    except StreamAbortError:
                                        # Flush buffer before terminating
                                        self._flush_assistant_buffer(
                                            project_dialog, dialog_id, assistant_buffer
                                        )
                                        yield SSEEventFactory.done(
                                            dialog_id=dialog_id
                                        ).to_sse()
                                        return
                                api_logger.info(
                                    f"Finished streaming {chunk_count} chunks from {key}"
                                )
                            elif asyncio.iscoroutine(response):
                                actual_response = await response
                                if hasattr(actual_response, "__aiter__"):
                                    chunk_count = 0
                                    async for chunk in actual_response:
                                        chunk_count += 1
                                        try:
                                            async for (
                                                sse_event
                                            ) in self._process_structured_chunk(
                                                chunk,
                                                dialog_id,
                                                assistant_buffer,
                                                project_dialog,
                                                reasoning_buffer,
                                            ):
                                                yield sse_event
                                        except StreamAbortError:
                                            yield SSEEventFactory.done(
                                                dialog_id=dialog_id
                                            ).to_sse()
                                            return
                                    api_logger.info(
                                        f"Finished streaming {chunk_count} chunks from {key}"
                                    )
                                else:
                                    try:
                                        async for (
                                            sse_event
                                        ) in self._process_structured_chunk(
                                            actual_response,
                                            dialog_id,
                                            assistant_buffer,
                                            project_dialog,
                                            reasoning_buffer,
                                        ):
                                            yield sse_event
                                    except StreamAbortError:
                                        # Flush buffer before terminating
                                        self._flush_assistant_buffer(
                                            project_dialog, dialog_id, assistant_buffer
                                        )
                                        yield SSEEventFactory.done(
                                            dialog_id=dialog_id
                                        ).to_sse()
                                        return

            # Persist streamed assistant text to dialog history (if available)
            self._flush_assistant_buffer(project_dialog, dialog_id, assistant_buffer)

            api_logger.info("SSE generation completed", total_events=event_count)
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()

        except asyncio.CancelledError:
            api_logger.info("Stream cancelled due to shutdown")
            # Flush buffer before exit
            self._flush_assistant_buffer(project_dialog, dialog_id, assistant_buffer)
            yield SSEEventFactory.error(
                message="Request cancelled due to server shutdown", dialog_id=dialog_id
            ).to_sse()
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
            raise
        except Exception as e:
            api_logger.error("Error in SSE generation", exc_info=True, error=str(e))
            # Flush buffer on error before signaling done
            self._flush_assistant_buffer(project_dialog, dialog_id, assistant_buffer)
            error_msg = f"Error processing request: {str(e)}"
            api_logger.error(f"Yielding error event: {error_msg}")
            yield SSEEventFactory.error(message=error_msg, dialog_id=dialog_id).to_sse()
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
        finally:
            # Remove task from active streams
            if current_task and current_task in self._active_streams:
                self._active_streams.discard(current_task)

    async def chat(
        self,
        query: str,
        context: dict[str, Any],
        dialog_id: str | None = None,
        project: Any | None = None,
    ) -> dict[str, Any]:
        orchestrator = self._get_orchestrator()
        # Centralize history: append user and inject dialog messages into context
        context = self._append_user_and_prepare_context(
            query, context, dialog_id, project
        )
        result = await orchestrator.process_request(
            query=query, context=context, stream=False
        )

        # Persist non-streaming assistant/tool messages
        try:
            if project and dialog_id:
                history = project.get_dialog_history(dialog_id)
                assistant_text = ""
                resp = result.get("response")
                conversation = []

                if isinstance(resp, str):
                    assistant_text = resp
                elif isinstance(resp, dict):
                    assistant_text = str(
                        resp.get("content") or resp.get("explanation") or ""
                    )
                    conversation = resp.get("conversation", [])

                if conversation:
                    # Build map of non-ephemeral tool_call_ids by inspecting ToolMessage-like entries
                    non_ephemeral_ids: set[str] = set()
                    for msg in conversation:
                        try:
                            tool_call_id = getattr(msg, "tool_call_id", None)
                            if isinstance(tool_call_id, str) and tool_call_id:
                                content = getattr(msg, "content", None)
                                if isinstance(content, str):
                                    try:
                                        parsed = json.loads(content)
                                    except Exception:
                                        parsed = None
                                    if isinstance(parsed, dict) and parsed.get(
                                        "result_ref"
                                    ):
                                        non_ephemeral_ids.add(tool_call_id)
                        except Exception:
                            # Best-effort; if parsing fails, treat as ephemeral by omission
                            pass

                    # Persist only AI messages with filtered tool_calls; skip ToolMessage entirely
                    for msg in conversation:
                        try:
                            tool_calls = getattr(msg, "tool_calls", None)
                        except Exception:
                            tool_calls = None

                        if tool_calls:
                            # Filter out ephemeral tool calls by checking for corresponding non-ephemeral ToolMessage ids
                            filtered_calls = []
                            for tc in (
                                list(tool_calls) if isinstance(tool_calls, list) else []
                            ):
                                try:
                                    tc_id = (
                                        tc.get("id")
                                        if isinstance(tc, dict)
                                        else getattr(tc, "id", "")
                                    )
                                except Exception:
                                    tc_id = ""
                                if tc_id and tc_id in non_ephemeral_ids:
                                    filtered_calls.append(tc)

                            try:
                                from langchain_core.messages import (
                                    AIMessage,
                                )

                                persisted = AIMessage(
                                    content=getattr(msg, "content", ""),
                                    tool_calls=filtered_calls,
                                )
                                try:
                                    existing_kwargs = dict(
                                        getattr(msg, "additional_kwargs", {}) or {}
                                    )
                                    existing_kwargs["tool_calls"] = filtered_calls
                                    persisted.additional_kwargs = existing_kwargs
                                except Exception:
                                    pass
                                history.add_message(persisted)
                            except Exception:
                                # Fallback to original message if AIMessage construction fails
                                history.add_message(msg)
                        else:
                            # Skip ToolMessage (has tool_call_id) to avoid storing inline results
                            if hasattr(msg, "tool_call_id") and getattr(
                                msg, "tool_call_id", None
                            ):
                                continue
                            # Other message types are ignored here

                if assistant_text:
                    conv_contents = (
                        [getattr(m, "content", "") for m in conversation]
                        if conversation
                        else []
                    )
                    if assistant_text not in conv_contents:
                        history.add_ai_message(assistant_text)
        except Exception as e:
            api_logger.error(
                "Failed to append assistant message (non-stream)",
                exc_info=True,
                error=str(e),
            )

        return result
