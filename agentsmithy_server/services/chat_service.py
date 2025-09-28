"""Chat service: orchestrates agent processing and yields domain events.

This service centralizes streaming/non-streaming chat logic so routers remain thin.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory
from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.core.dialog_summary_storage import DialogSummaryStorage
from agentsmithy_server.core.summarization.strategy import KEEP_LAST_MESSAGES
from agentsmithy_server.utils.logger import api_logger


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
    ) -> None:
        """Persist accumulated assistant text to dialog history (best-effort)."""
        try:
            if assistant_buffer and project_dialog:
                project_obj, pdialog_id = project_dialog
                target_dialog_id = dialog_id or pdialog_id
                if target_dialog_id and hasattr(project_obj, "get_dialog_history"):
                    history = project_obj.get_dialog_history(target_dialog_id)
                    content = "".join(assistant_buffer)
                    if content:
                        history.add_ai_message(content)
        except Exception as e:
            api_logger.error("Failed to append assistant message (stream)", exception=e)

    def _get_orchestrator(self) -> AgentOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = AgentOrchestrator()
        return self._orchestrator

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
    ) -> AsyncIterator[dict[str, str]]:
        if isinstance(chunk, dict) and chunk.get("type") in {
            "file_edit",
            "tool_call",
            "error",
            "chat",
            "reasoning",
            "chat_start",
            "chat_end",
            "reasoning_start",
            "reasoning_end",
            "summary_start",
            "summary_end",
        }:
            if chunk["type"] == "chat":
                content = chunk.get("content", "")
                if content:
                    assistant_buffer.append(content)
                    yield SSEEventFactory.chat(
                        content=content, dialog_id=dialog_id
                    ).to_sse()
            elif chunk["type"] == "reasoning":
                content = chunk.get("content", "")
                if content:
                    yield SSEEventFactory.reasoning(
                        content=content, dialog_id=dialog_id
                    ).to_sse()
            elif chunk["type"] == "chat_start":
                yield SSEEventFactory.chat_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "chat_end":
                yield SSEEventFactory.chat_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "reasoning_start":
                yield SSEEventFactory.reasoning_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "reasoning_end":
                yield SSEEventFactory.reasoning_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "summary_start":
                yield SSEEventFactory.summary_start(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "summary_end":
                yield SSEEventFactory.summary_end(dialog_id=dialog_id).to_sse()
            elif chunk["type"] == "file_edit":
                yield SSEEventFactory.file_edit(
                    file=chunk.get("file", ""),
                    diff=chunk.get("diff"),
                    checkpoint=chunk.get("checkpoint"),
                    dialog_id=dialog_id,
                ).to_sse()
            elif chunk["type"] == "tool_call":
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
                if tool_event.get("type") == "tool_call":
                    sse = SSEEventFactory.tool_call(
                        name=tool_event.get("name", ""),
                        args=tool_event.get("args", {}),
                        dialog_id=dialog_id,
                    ).to_sse()
                elif tool_event.get("type") == "file_edit":
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
                api_logger.stream_log("tool_event", None)
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
            api_logger.error("Failed to append user message", exception=e)

        # Load history; use persisted summary when present
        messages = []
        summary_text = None
        try:
            # Try persisted summary to decide whether to load only tail K
            try:
                storage = DialogSummaryStorage(project, dialog_id)
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
            api_logger.error("Failed to load dialog history", exception=e)

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
                                    chunk, dialog_id, assistant_buffer
                                ):
                                    yield sse_event
                                api_logger.stream_log(
                                    "processed_chunk", None, chunk_number=chunk_count
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
                                state["response"], dialog_id, assistant_buffer
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
                                            chunk, dialog_id, assistant_buffer
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
                                                chunk, dialog_id, assistant_buffer
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
                                            actual_response, dialog_id, assistant_buffer
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
            api_logger.error("Error in SSE generation", exception=e)
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
                    for msg in conversation:
                        if hasattr(msg, "tool_calls") and getattr(
                            msg, "tool_calls", None
                        ):
                            history.add_message(msg)
                        elif hasattr(msg, "tool_call_id") and getattr(
                            msg, "tool_call_id", None
                        ):
                            history.add_message(msg)

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
                "Failed to append assistant message (non-stream)", exception=e
            )

        return result
