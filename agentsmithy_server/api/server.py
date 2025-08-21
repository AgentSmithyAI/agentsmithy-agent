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
from agentsmithy_server.config import settings  # re-export for external imports

from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.core.dialog_io import (
    DialogMessage,
    append_message,
    append_sse_event,
    read_messages,
)
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
    """Generate SSE events for streaming response."""
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

            # Send task type when classified
            if state.get("task_type") and not state.get("response"):
                event_dict = {
                    "data": json.dumps(
                        {
                            "type": "classification",
                            "task_type": state["task_type"],
                            "dialog_id": project_dialog[1] if project_dialog else None,
                        }
                    )
                }
                if project_dialog:
                    try:
                        append_sse_event(
                            project_dialog[0],
                            project_dialog[1],
                            json.loads(event_dict["data"]),
                        )
                    except Exception as e:
                        api_logger.error("Failed to append SSE event", exception=e)
                api_logger.stream_log(
                    "classification", state["task_type"], event_number=event_count
                )
                yield event_dict

            # Check for task_type in classifier state
            if "classifier" in state and isinstance(state["classifier"], dict):
                classifier_data = state["classifier"]
                if "task_type" in classifier_data and classifier_data["task_type"]:
                    event_dict = {
                        "data": json.dumps(
                            {
                                "type": "classification",
                                "task_type": classifier_data["task_type"],
                                "dialog_id": (
                                    project_dialog[1] if project_dialog else None
                                ),
                            }
                        )
                    }
                    if project_dialog:
                        try:
                            append_sse_event(
                                project_dialog[0],
                                project_dialog[1],
                                json.loads(event_dict["data"]),
                            )
                        except Exception as e:
                            api_logger.error("Failed to append SSE event", exception=e)
                    yield event_dict

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
                        # Check if chunk contains structured data (diffs/edits)
                        if isinstance(chunk, dict):
                            # Handle structured responses (file operations/tool results)
                            if chunk.get("type") in [
                                "diff",
                                "file_change",
                                "edit",
                                "change_applied",
                                "file_patched",
                                "tool_result",
                            ]:
                                payload = dict(chunk)
                                payload["dialog_id"] = (
                                    project_dialog[1] if project_dialog else None
                                )
                                event_dict = {"data": json.dumps(payload)}
                                api_logger.stream_log(
                                    "file_operation", None, chunk_number=chunk_count
                                )
                                if project_dialog:
                                    try:
                                        append_sse_event(
                                            project_dialog[0],
                                            project_dialog[1],
                                            payload,
                                        )
                                    except Exception as e:
                                        api_logger.error(
                                            "Failed to append SSE event", exception=e
                                        )
                                yield event_dict
                            else:
                                # Regular content
                                event_dict = {
                                    "data": json.dumps(
                                        {
                                            "content": chunk.get(
                                                "content", chunk.get("data", str(chunk))
                                            ),
                                            "dialog_id": (
                                                project_dialog[1]
                                                if project_dialog
                                                else None
                                            ),
                                        }
                                    )
                                }
                                if project_dialog:
                                    try:
                                        append_sse_event(
                                            project_dialog[0],
                                            project_dialog[1],
                                            json.loads(event_dict["data"]),
                                        )
                                    except Exception as e:
                                        api_logger.error(
                                            "Failed to append SSE event", exception=e
                                        )
                                yield event_dict
                        else:
                            # Regular text content
                            event_dict = {
                                "data": json.dumps(
                                    {
                                        "content": chunk,
                                        "dialog_id": (
                                            project_dialog[1]
                                            if project_dialog
                                            else None
                                        ),
                                    }
                                )
                            }
                            api_logger.stream_log(
                                "content_chunk", chunk, chunk_number=chunk_count
                            )
                            assistant_buffer.append(str(chunk))
                            if project_dialog:
                                try:
                                    append_sse_event(
                                        project_dialog[0],
                                        project_dialog[1],
                                        json.loads(event_dict["data"]),
                                    )
                                except Exception as e:
                                    api_logger.error(
                                        "Failed to append SSE event", exception=e
                                    )
                            yield event_dict

                        # Check for tool events in queue (non-blocking)
                        try:
                            while not sse_events_queue.empty():
                                tool_event = await asyncio.wait_for(
                                    sse_events_queue.get(), timeout=0.01
                                )
                                # Attach dialog_id to tool events as metadata
                                te = dict(tool_event)
                                if project_dialog:
                                    te.setdefault("metadata", {})
                                    if isinstance(te["metadata"], dict):
                                        te["metadata"]["dialog_id"] = project_dialog[1]
                                event_dict = {"data": json.dumps(te)}
                                api_logger.stream_log(
                                    "tool_event", json.dumps(tool_event)[:100]
                                )
                                if project_dialog:
                                    try:
                                        append_sse_event(
                                            project_dialog[0], project_dialog[1], te
                                        )
                                    except Exception as e:
                                        api_logger.error(
                                            "Failed to append SSE event", exception=e
                                        )
                                yield event_dict
                        except TimeoutError:
                            pass
                    api_logger.info(f"Finished streaming {chunk_count} chunks")
                else:
                    # It's a complete response
                    if isinstance(state["response"], dict):
                        # Check if it's structured response with file operations
                        if "file_operations" in state["response"]:
                            # Send explanation first
                            if state["response"].get("explanation"):
                                explanation_event = {
                                    "data": json.dumps(
                                        {
                                            "content": state["response"]["explanation"],
                                            "dialog_id": (
                                                project_dialog[1]
                                                if project_dialog
                                                else None
                                            ),
                                        }
                                    )
                                }
                                if project_dialog:
                                    try:
                                        append_sse_event(
                                            project_dialog[0],
                                            project_dialog[1],
                                            json.loads(explanation_event["data"]),
                                        )
                                    except Exception as e:
                                        api_logger.error(
                                            "Failed to append SSE event", exception=e
                                        )
                                yield explanation_event

                            # Send file operations as separate events
                            for operation in state["response"]["file_operations"]:
                                if operation.get("type") == "edit":
                                    diff_event = {
                                        "data": json.dumps(
                                            {
                                                "type": "diff",
                                                "file": operation["file"],
                                                "diff": operation["diff"],
                                                "line_start": operation.get(
                                                    "line_start"
                                                ),
                                                "line_end": operation.get("line_end"),
                                                "reason": operation.get("reason"),
                                                "dialog_id": (
                                                    project_dialog[1]
                                                    if project_dialog
                                                    else None
                                                ),
                                            }
                                        )
                                    }
                                    api_logger.info(
                                        "Sending diff", file=operation["file"]
                                    )
                                    if project_dialog:
                                        try:
                                            append_sse_event(
                                                project_dialog[0],
                                                project_dialog[1],
                                                json.loads(diff_event["data"]),
                                            )
                                        except Exception as e:
                                            api_logger.error(
                                                "Failed to append SSE event",
                                                exception=e,
                                            )
                                    yield diff_event
                        else:
                            # Regular structured response
                            event_dict = {
                                "data": json.dumps(
                                    {
                                        "content": str(state["response"]),
                                        "dialog_id": (
                                            project_dialog[1]
                                            if project_dialog
                                            else None
                                        ),
                                    }
                                )
                            }
                            if project_dialog:
                                try:
                                    append_sse_event(
                                        project_dialog[0],
                                        project_dialog[1],
                                        json.loads(event_dict["data"]),
                                    )
                                except Exception as e:
                                    api_logger.error(
                                        "Failed to append SSE event", exception=e
                                    )
                            yield event_dict
                    else:
                        # Regular text response
                        event_dict = {
                            "data": json.dumps(
                                {
                                    "content": state["response"],
                                    "dialog_id": (
                                        project_dialog[1] if project_dialog else None
                                    ),
                                }
                            )
                        }
                        api_logger.stream_log("content_complete", state["response"])
                        assistant_buffer.append(str(state["response"]))
                        if project_dialog:
                            try:
                                append_sse_event(
                                    project_dialog[0],
                                    project_dialog[1],
                                    json.loads(event_dict["data"]),
                                )
                            except Exception as e:
                                api_logger.error(
                                    "Failed to append SSE event", exception=e
                                )
                        yield event_dict

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
                                # Wrap chunk in proper JSON format
                                event_dict = {
                                    "data": json.dumps(
                                        {
                                            "content": chunk,
                                            "dialog_id": (
                                                project_dialog[1]
                                                if project_dialog
                                                else None
                                            ),
                                        }
                                    )
                                }
                                yield event_dict
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
                                    # Wrap chunk in proper JSON format
                                    event_dict = {
                                        "data": json.dumps(
                                            {
                                                "content": chunk,
                                                "dialog_id": (
                                                    project_dialog[1]
                                                    if project_dialog
                                                    else None
                                                ),
                                            }
                                        )
                                    }
                                    yield event_dict
                                api_logger.info(
                                    f"Finished streaming {chunk_count} chunks from {key}"
                                )
                            else:
                                # Non-streaming response
                                # Wrap response in proper JSON format
                                event_dict = {
                                    "data": json.dumps(
                                        {
                                            "content": actual_response,
                                            "dialog_id": (
                                                project_dialog[1]
                                                if project_dialog
                                                else None
                                            ),
                                        }
                                    )
                                }
                                yield event_dict

        # Persist assistant response if dialog logging is enabled
        if project_dialog and assistant_buffer:
            project, dialog_id = project_dialog
            try:
                append_message(
                    project,
                    dialog_id,
                    DialogMessage(role="assistant", content="".join(assistant_buffer)),
                )
            except Exception as e:
                api_logger.error("Failed to append assistant message", exception=e)

        # Send completion signal
        api_logger.info("SSE generation completed", total_events=event_count)
        completion_dict = {
            "data": json.dumps(
                {
                    "done": True,
                    "dialog_id": project_dialog[1] if project_dialog else None,
                }
            )
        }
        if project_dialog:
            try:
                append_sse_event(
                    project_dialog[0],
                    project_dialog[1],
                    json.loads(completion_dict["data"]),
                )
            except Exception as e:
                api_logger.error("Failed to append SSE event", exception=e)
        yield completion_dict

    except Exception as e:
        api_logger.error("Error in SSE generation", exception=e)
        error_msg = f"Error processing request: {str(e)}"
        error_dict = {"data": json.dumps({"error": error_msg})}
        api_logger.error(f"Yielding error event: {error_dict}")
        yield error_dict


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

        # Append user message to dialog log
        try:
            append_message(
                project, dialog_id, DialogMessage(role="user", content=user_message)
            )
        except Exception as e:
            api_logger.error("Failed to append user message", exception=e)

        # Load recent dialog messages for context (e.g., last 20)
        recent_messages = []
        try:
            recent_messages = read_messages(project, dialog_id, limit=20)
        except Exception as e:
            api_logger.error("Failed to read dialog messages", exception=e)

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
                if isinstance(resp, str):
                    assistant_text = resp
                elif isinstance(resp, dict):
                    assistant_text = str(
                        resp.get("content") or resp.get("explanation") or ""
                    )
                if assistant_text:
                    append_message(
                        project,
                        dialog_id,
                        DialogMessage(role="assistant", content=assistant_text),
                    )
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
