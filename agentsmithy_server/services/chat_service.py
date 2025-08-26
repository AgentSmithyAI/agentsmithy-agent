"""Chat service: orchestrates agent processing and yields domain events.

This service centralizes streaming/non-streaming chat logic so routers remain thin.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import asyncio
from typing import Any

from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory
from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.utils.logger import api_logger


class StreamAbortError(Exception):
    """Signal to abort streaming due to error."""


class ChatService:
    def __init__(self) -> None:
        self._orchestrator: AgentOrchestrator | None = None

    def _get_orchestrator(self) -> AgentOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = AgentOrchestrator()
        return self._orchestrator

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
            except (asyncio.TimeoutError, TimeoutError):
                break

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

    async def _drain_until_types(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        dialog_id: str | None,
        target_types: set[str],
        max_wait_seconds: float = 2.0,
    ) -> list[dict[str, str]]:
        """Aggressively drain queue until one of target_types is observed or timeout.

        Used to surface file_edit immediately after a tool_call.
        """
        sse_events: list[dict[str, str]] = []
        found = False
        # Try small timed pulls up to max_wait_seconds
        interval = 0.05
        attempts = max(1, int(max_wait_seconds / interval))
        for _ in range(attempts):
            try:
                tool_event = await asyncio.wait_for(queue.get(), timeout=interval)
            except (asyncio.TimeoutError, TimeoutError):
                if found:
                    break
                continue

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
            sse_events.append(sse)
            if tool_event.get("type") in target_types:
                found = True

        return sse_events

    async def stream_chat(
        self,
        query: str,
        context: dict[str, Any],
        dialog_id: str | None,
        project_dialog: tuple[Any, str] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        api_logger.info("Starting SSE event generation", query=query[:100])

        sse_events_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def sse_callback(event_data: dict[str, Any]):
            await sse_events_queue.put(event_data)

        orchestrator = self._get_orchestrator()
        if hasattr(orchestrator, "set_sse_callback"):
            orchestrator.set_sse_callback(sse_callback)

        try:
            api_logger.debug("Processing request with orchestrator", streaming=True)
            result = await orchestrator.process_request(
                query=query, context=context, stream=True
            )
            graph_execution = result["graph_execution"]
            api_logger.debug("Graph execution started")

            event_count = 0
            assistant_buffer: list[str] = []

            async for state in graph_execution:
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
                        # Iterate manually to flush file_edit immediately after tool_call
                        chunk_count = 0
                        iterator = state["response"].__aiter__()
                        while True:
                            try:
                                chunk = await iterator.__anext__()
                            except StopAsyncIteration:
                                break
                            chunk_count += 1
                            try:
                                # If tool_call, yield it then aggressively drain until file_edit
                                if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                                    async for sse_event in self._process_structured_chunk(
                                        chunk, dialog_id, assistant_buffer
                                    ):
                                        yield sse_event
                                    # Drain until we see file_edit or timeout
                                    for sse in await self._drain_until_types(
                                        sse_events_queue, dialog_id, {"file_edit"}
                                    ):
                                        yield sse
                                else:
                                    async for sse_event in self._process_structured_chunk(
                                        chunk, dialog_id, assistant_buffer
                                    ):
                                        yield sse_event
                                    # Regular small drain
                                    for sse in await self._drain_tool_events_queue(
                                        sse_events_queue, dialog_id
                                    ):
                                        yield sse
                                api_logger.stream_log(
                                    "processed_chunk", None, chunk_number=chunk_count
                                )
                            except StreamAbortError:
                                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                                return
                        api_logger.info(f"Finished streaming {chunk_count} chunks")
                        # Final drain to ensure tool events (e.g., file_edit) are flushed
                        for sse in await self._drain_tool_events_queue(
                            sse_events_queue, dialog_id
                        ):
                            yield sse
                    else:
                        try:
                            async for sse_event in self._process_structured_chunk(
                                state["response"], dialog_id, assistant_buffer
                            ):
                                yield sse_event
                        except StreamAbortError:
                            pass

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
                                        yield SSEEventFactory.done(
                                            dialog_id=dialog_id
                                        ).to_sse()
                                        return
                                # Drain tool events (e.g., file_edit) that may have arrived during streaming
                                for sse in await self._drain_tool_events_queue(
                                    sse_events_queue, dialog_id
                                ):
                                    yield sse
                                api_logger.info(
                                    f"Finished streaming {chunk_count} chunks from {key}"
                                )
                                # Final drain to ensure no pending tool events remain
                                for sse in await self._drain_tool_events_queue(
                                    sse_events_queue, dialog_id
                                ):
                                    yield sse
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
                                        # Drain tool events (e.g., file_edit) that may have arrived during streaming
                                        for sse in await self._drain_tool_events_queue(
                                            sse_events_queue, dialog_id
                                        ):
                                            yield sse
                                    api_logger.info(
                                        f"Finished streaming {chunk_count} chunks from {key}"
                                    )
                                    # Final drain to ensure no pending tool events remain
                                    for sse in await self._drain_tool_events_queue(
                                        sse_events_queue, dialog_id
                                    ):
                                        yield sse
                                else:
                                    try:
                                        async for (
                                            sse_event
                                        ) in self._process_structured_chunk(
                                            actual_response, dialog_id, assistant_buffer
                                        ):
                                            yield sse_event
                                    except StreamAbortError:
                                        pass
                                    # Drain tool events after processing non-iterable response
                                    for sse in await self._drain_tool_events_queue(
                                        sse_events_queue, dialog_id
                                    ):
                                        yield sse

            # Persist handled by router after buffer is returned via closure
            api_logger.info("SSE generation completed", total_events=event_count)
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()

        except Exception as e:
            api_logger.error("Error in SSE generation", exception=e)
            error_msg = f"Error processing request: {str(e)}"
            api_logger.error(f"Yielding error event: {error_msg}")
            yield SSEEventFactory.error(message=error_msg, dialog_id=dialog_id).to_sse()
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()

    async def chat(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        orchestrator = self._get_orchestrator()
        return await orchestrator.process_request(
            query=query, context=context, stream=False
        )
