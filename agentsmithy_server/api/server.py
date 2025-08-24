"""FastAPI server for AgentSmithy."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentsmithy_server.api.sse_protocol import (
    EventFactory as SSEEventFactory,
)
from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.core.project import get_current_project
from agentsmithy_server.utils.logger import api_logger


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    context: dict[str, Any] = {}
    stream: bool = True
    dialog_id: str | None = None


class ChatResponse(BaseModel):
    content: str
    done: bool = False
    metadata: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "agentsmithy-server"


# Dialog models
class DialogCreateRequest(BaseModel):
    title: str | None = None
    set_current: bool = True


class DialogPatchRequest(BaseModel):
    title: str | None = None


class DialogListParams(BaseModel):
    sort: str = "last_message_at"  # created_at|updated_at|last_message_at
    order: str = "desc"  # asc|desc
    limit: int | None = 50
    offset: int = 0


# Initialize FastAPI app
app = FastAPI(
    title="AgentSmithy Server",
    description="AI agent server similar to Cursor, powered by LangGraph",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator lazily to avoid import-time side effects
orchestrator: AgentOrchestrator | None = None


def _get_dialog_id(project_dialog: tuple[Any, str] | None) -> str | None:
    """Safely extract dialog_id from a `(project, dialog_id)` tuple.

    Returns None when dialog info is not available.
    """
    return project_dialog[1] if project_dialog else None





def _sse_chat(content: str, dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.chat(content=content, dialog_id=dialog_id).to_sse()


def _sse_reasoning(content: str, dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.reasoning(content=content, dialog_id=dialog_id).to_sse()


def _sse_tool_call(name: str, args: dict[str, Any], dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.tool_call(name=name, args=args, dialog_id=dialog_id).to_sse()


def _sse_file_edit(file: str, dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.file_edit(file=file, dialog_id=dialog_id).to_sse()


def _sse_error(message: str, dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.error(message=message, dialog_id=dialog_id).to_sse()


def _sse_done(dialog_id: str | None) -> dict[str, str]:
    return SSEEventFactory.done(dialog_id=dialog_id).to_sse()


class StreamAbortError(Exception):
    """Signal to abort streaming due to error."""
    pass


async def _process_structured_chunk(
    chunk: Any,
    dialog_id: str | None,
    assistant_buffer: list[str],
) -> AsyncIterator[dict[str, str]]:
    """Process a single chunk and yield appropriate SSE events.
    
    Raises StreamAbortError if error event is encountered.
    """
    if isinstance(chunk, dict) and chunk.get("type") in {"file_edit", "tool_call", "error", "chat", "reasoning"}:
        if chunk["type"] == "chat":
            content = chunk.get("content", "")
            if content:
                assistant_buffer.append(content)
                yield _sse_chat(content=content, dialog_id=dialog_id)
        elif chunk["type"] == "reasoning":
            content = chunk.get("content", "")
            if content:
                yield _sse_reasoning(content=content, dialog_id=dialog_id)
        elif chunk["type"] == "file_edit":
            yield _sse_file_edit(file=chunk.get("file", ""), dialog_id=dialog_id)
        elif chunk["type"] == "tool_call":
            yield _sse_tool_call(name=chunk.get("name", ""), args=chunk.get("args", {}), dialog_id=dialog_id)
        else:
            # Emit error and signal abort
            yield _sse_error(message=chunk.get("error", ""), dialog_id=dialog_id)
            raise StreamAbortError()  # Signal to abort streaming
    elif isinstance(chunk, str):
        assistant_buffer.append(chunk)
        yield _sse_chat(content=chunk, dialog_id=dialog_id)
    else:
        # Unknown type - convert to string as last resort
        content = str(chunk)
        assistant_buffer.append(content)
        yield _sse_chat(content=content, dialog_id=dialog_id)


async def _drain_tool_events_queue(
    queue: asyncio.Queue[dict[str, Any]], dialog_id: str | None
) -> list[dict[str, str]]:
    """Drain queued tool events and convert to SSE dicts.

    Non-blocking with a short timeout per pop; returns a list of SSE events.
    """
    sse_events: list[dict[str, str]] = []
    try:
        while not queue.empty():
            tool_event = await asyncio.wait_for(queue.get(), timeout=0.01)
            if tool_event.get("type") == "tool_call":
                sse = _sse_tool_call(
                    name=tool_event.get("name", ""),
                    args=tool_event.get("args", {}),
                    dialog_id=dialog_id,
                )
            elif tool_event.get("type") == "file_edit":
                sse = _sse_file_edit(file=tool_event.get("file", ""), dialog_id=dialog_id)
            elif tool_event.get("type") == "error":
                sse = _sse_error(message=tool_event.get("error", ""), dialog_id=dialog_id)
            else:
                # Fallback: stream as chat event
                sse = _sse_chat(content=str(tool_event), dialog_id=dialog_id)
            api_logger.stream_log("tool_event", json.dumps(tool_event)[:100])
            sse_events.append(sse)
    except TimeoutError:
        pass
    return sse_events


@app.on_event("startup")
async def _init_dialogs_state() -> None:
    """Ensure dialogs state exists; create a default dialog if none present."""
    try:
        project = get_current_project()
        project.ensure_dialogs_dir()
        index = project.load_dialogs_index()
        dialogs = index.get("dialogs") or []
        if not dialogs:
            project.create_dialog(title="default", set_current=True)
    except Exception as e:
        # Non-fatal: server can still operate; chat path will auto-create
        api_logger.error("Dialog state init failed", exception=e)

    # Create orchestrator on startup (runtime env should be configured here)
    try:
        global orchestrator
        orchestrator = AgentOrchestrator()
    except Exception as e:
        api_logger.error("AgentOrchestrator init failed", exception=e)


async def generate_sse_events(
    query: str,
    context: dict[str, Any],
    project_dialog: tuple[Any, str] | None,
) -> AsyncIterator[dict[str, Any]]:  # Changed return type
    """Generate SSE events for streaming response.

    High-level flow:
    - Set up an internal queue to receive tool events (tool_call, file_edit, error)
    - Ask the orchestrator to process the request with streaming
    - For every graph state update, stream content chunks and drain tool events
    - Persist the final assistant message into dialog history
    - Emit a final done event (or error when exceptions occur)
    """
    api_logger.info("Starting SSE event generation", query=query[:100])

    # Define SSE callback for tool results
    sse_events_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def sse_callback(event_data: dict[str, Any]):
        """Callback to queue SSE events from tools."""
        await sse_events_queue.put(event_data)

    # Set the callback on orchestrator
    if orchestrator and hasattr(orchestrator, "set_sse_callback"):
        orchestrator.set_sse_callback(sse_callback)

    try:
        # Process request with streaming
        api_logger.debug("Processing request with orchestrator", streaming=True)
        if orchestrator is None:
            raise RuntimeError("Orchestrator not initialized")
        result = await orchestrator.process_request(
            query=query, context=context, stream=True
        )

        graph_execution = result["graph_execution"]
        api_logger.debug("Graph execution started")

        # Stream intermediate updates
        event_count = 0

        # Buffer to persist assistant message at end
        assistant_buffer: list[str] = []

        async for state in graph_execution:
            event_count += 1
            api_logger.debug(
                f"Processing state #{event_count}", state_keys=list(state.keys())
            )

            # Simplified protocol: no classification events

            # Stream the response if it's an async generator
            if state.get("response"):
                api_logger.debug(
                    "Processing response",
                    has_aiter=hasattr(state["response"], "__aiter__"),
                )

                if hasattr(state["response"], "__aiter__"):
                    # It's an async generator (streaming response)
                    chunk_count = 0
                    async for chunk in state["response"]:
                        chunk_count += 1
                        try:
                            async for sse_event in _process_structured_chunk(
                                chunk, _get_dialog_id(project_dialog), assistant_buffer
                            ):
                                yield sse_event
                            api_logger.stream_log("processed_chunk", None, chunk_number=chunk_count)
                        except StreamAbortError:
                            # Error event was emitted, abort streaming
                            return

                        # Non-blocking drain of tool events queued by tools
                        for sse in await _drain_tool_events_queue(sse_events_queue, _get_dialog_id(project_dialog)):
                            yield sse
                    api_logger.info(f"Finished streaming {chunk_count} chunks")
                else:
                    # It's a complete response
                    try:
                        async for sse_event in _process_structured_chunk(
                            state["response"], _get_dialog_id(project_dialog), assistant_buffer
                        ):
                            yield sse_event
                    except StreamAbortError:
                        # Error event was emitted
                        pass

            # Check for response in agent-specific keys
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
                                    async for sse_event in _process_structured_chunk(
                                        chunk, _get_dialog_id(project_dialog), assistant_buffer
                                    ):
                                        yield sse_event
                                except StreamAbortError:
                                    # Error event was emitted, abort streaming
                                    return
                            api_logger.info(
                                f"Finished streaming {chunk_count} chunks from {key}"
                            )
                        elif asyncio.iscoroutine(response):
                            # It's a coroutine that returns an async generator
                            actual_response = await response

                            if hasattr(actual_response, "__aiter__"):
                                chunk_count = 0
                                async for chunk in actual_response:
                                    chunk_count += 1
                                    try:
                                        async for sse_event in _process_structured_chunk(
                                            chunk, _get_dialog_id(project_dialog), assistant_buffer
                                        ):
                                            yield sse_event
                                    except StreamAbortError:
                                        # Error event was emitted, abort streaming
                                        return
                                api_logger.info(
                                    f"Finished streaming {chunk_count} chunks from {key}"
                                )
                            else:
                                # Non-streaming response
                                try:
                                    async for sse_event in _process_structured_chunk(
                                        actual_response, _get_dialog_id(project_dialog), assistant_buffer
                                    ):
                                        yield sse_event
                                except StreamAbortError:
                                    # Error event was emitted
                                    pass

        # Persist assistant response if dialog logging is enabled
        if project_dialog:
            project, dialog_id = project_dialog
            try:
                content_joined = "".join(assistant_buffer).strip()
                api_logger.info(
                    "Persisting assistant message",
                    buffer_size=len(assistant_buffer),
                    content_length=len(content_joined),
                    has_content=bool(content_joined),
                )
                if content_joined:
                    dialog_history = project.get_dialog_history(dialog_id)
                    dialog_history.add_ai_message(content_joined)
                    api_logger.info("Assistant message persisted successfully")
            except Exception as e:
                api_logger.error("Failed to append assistant message", exception=e)

        # Send completion signal
        api_logger.info("SSE generation completed", total_events=event_count)
        yield _sse_done(dialog_id=_get_dialog_id(project_dialog))

    except Exception as e:
        api_logger.error("Error in SSE generation", exception=e)
        error_msg = f"Error processing request: {str(e)}"
        api_logger.error(f"Yielding error event: {error_msg}")
        yield _sse_error(message=error_msg, dialog_id=_get_dialog_id(project_dialog))


@app.post("/api/chat")
async def chat(request: ChatRequest, raw_request: Request):
    """Handle chat requests with optional streaming."""
    start_time = time.time()
    client_host = raw_request.client.host if raw_request.client else "unknown"

    api_logger.info(
        "Chat request received",
        client=client_host,
        streaming=request.stream,
        message_count=len(request.messages),
        has_context="current_file" in request.context,
    )

    try:
        # Extract the latest user message
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break

        if not user_message:
            api_logger.warning("No user message found in request")
            raise HTTPException(status_code=400, detail="No user message found")

        api_logger.debug("User message extracted", message_length=len(user_message))

        # Prepare dialog storage
        project = get_current_project()

        # Decide dialog id
        dialog_id = request.dialog_id or project.get_current_dialog_id()
        if not dialog_id:
            dialog_id = project.create_dialog(set_current=True)

        # Get dialog history
        dialog_history = project.get_dialog_history(dialog_id)

        # Append user message to dialog history
        try:
            dialog_history.add_user_message(user_message)
        except Exception as e:
            api_logger.error("Failed to append user message", exception=e)

        # Load recent messages for context
        recent_messages = []
        try:
            messages = dialog_history.get_messages(limit=20)
            # Pass the actual message objects to preserve tool calls
            recent_messages = messages
        except Exception as e:
            api_logger.error("Failed to load dialog history", exception=e)

        # Inject dialog info into context
        request.context = dict(request.context or {})
        request.context["dialog"] = {"id": dialog_id, "messages": recent_messages}

        if request.stream:
            # Return SSE streaming response
            api_logger.info("Returning SSE streaming response")
            sse_response = EventSourceResponse(
                generate_sse_events(
                    user_message, request.context, (project, dialog_id)
                ),
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )

            # Log response time
            duration_ms = (time.time() - start_time) * 1000
            api_logger.request_log(
                "POST", "/api/chat", 200, duration_ms, streaming=True
            )

            return sse_response
        else:
            # Return regular JSON response
            api_logger.info("Processing non-streaming request")
            if orchestrator is None:
                raise RuntimeError("Orchestrator not initialized")
            result = await orchestrator.process_request(
                query=user_message, context=request.context, stream=False
            )

            # Persist assistant response to dialog log (best-effort)
            try:
                assistant_text = ""
                resp: Any = result.get("response")
                conversation = []

                if isinstance(resp, str):
                    assistant_text = resp
                elif isinstance(resp, dict):
                    assistant_text = str(
                        resp.get("content") or resp.get("explanation") or ""
                    )
                    conversation = resp.get("conversation", [])

                # Save full conversation history including tool calls
                dialog_history = project.get_dialog_history(dialog_id)

                # Save intermediate messages (tool calls and results)
                if conversation:
                    # Skip messages already in history and add only new ones
                    existing_msg_count = len(recent_messages)
                    for msg in conversation[
                        existing_msg_count + 1 :
                    ]:  # +1 for system message
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            # It's an AIMessage with tool calls
                            dialog_history.history.add_message(msg)  # type: ignore
                        elif hasattr(msg, "tool_call_id"):
                            # It's a ToolMessage
                            dialog_history.history.add_message(msg)  # type: ignore

                # Save final assistant message if it's different from tool response
                if assistant_text and (
                    not conversation
                    or assistant_text
                    not in [getattr(m, "content", "") for m in conversation]
                ):
                    dialog_history.add_ai_message(assistant_text)
            except Exception as e:
                api_logger.error(
                    "Failed to append assistant message (non-stream)", exception=e
                )

            json_response = ChatResponse(
                content=result["response"], done=True, metadata=result["metadata"]
            )

            # Log response time
            duration_ms = (time.time() - start_time) * 1000
            api_logger.request_log(
                "POST",
                "/api/chat",
                200,
                duration_ms,
                streaming=False,
                response_length=len(result["response"]),
            )

            return json_response

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        api_logger.error("Chat request failed", exception=e, duration_ms=duration_ms)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


@app.get("/")
async def root():
    """Root endpoint with usage information."""
    return {
        "title": "AgentSmithy Server",
        "description": "AI agent server similar to Cursor, powered by LangGraph",
        "endpoints": {
            "POST /api/chat": "Main chat endpoint (supports SSE streaming)",
            "GET /health": "Health check",
        },
        "usage": {
            "example_request": {
                "messages": [{"role": "user", "content": "Help me refactor this code"}],
                "context": {
                    "current_file": {
                        "path": "example.py",
                        "language": "python",
                        "content": "def calculate(x, y): return x + y",
                    }
                },
                "stream": True,
            }
        },
    }


# --- Dialogs CRUD ---


@app.get("/api/dialogs")
async def list_dialogs(
    sort: str = "last_message_at",
    order: str = "desc",
    limit: int | None = 50,
    offset: int = 0,
):
    project = get_current_project()
    descending = order.lower() != "asc"
    items = project.list_dialogs(
        sort_by=sort,
        descending=descending,
        limit=limit,
        offset=offset,
    )
    return {
        "current_dialog_id": project.get_current_dialog_id(),
        "dialogs": items,
    }


@app.post("/api/dialogs")
async def create_dialog(payload: DialogCreateRequest):
    project = get_current_project()
    dialog_id = project.create_dialog(
        title=payload.title, set_current=payload.set_current
    )
    return {"id": dialog_id}


@app.get("/api/dialogs/current")
async def get_current_dialog():
    project = get_current_project()
    cid = project.get_current_dialog_id()
    if not cid:
        return {"id": None}
    return {"id": cid, "meta": project.get_dialog_meta(cid)}


@app.patch("/api/dialogs/current")
async def set_current_dialog(id: str):
    project = get_current_project()
    project.set_current_dialog_id(id)
    return {"ok": True}


@app.get("/api/dialogs/{dialog_id}")
async def get_dialog(dialog_id: str):
    project = get_current_project()
    meta = project.get_dialog_meta(dialog_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dialog not found")
    return meta


@app.patch("/api/dialogs/{dialog_id}")
async def patch_dialog(dialog_id: str, payload: DialogPatchRequest):
    project = get_current_project()
    fields: dict[str, Any] = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if not fields:
        return {"ok": True}
    project.upsert_dialog_meta(dialog_id, **fields)
    return {"ok": True}


@app.delete("/api/dialogs/{dialog_id}")
async def delete_dialog(dialog_id: str):
    project = get_current_project()
    project.delete_dialog(dialog_id)
    return {"ok": True}
