from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from agentsmithy_server.api.deps import get_chat_service, get_project
from agentsmithy_server.api.schemas import ChatRequest, ChatResponse
from agentsmithy_server.api.sse import stream_response
from agentsmithy_server.core.project import Project
from agentsmithy_server.services.chat_service import ChatService
from agentsmithy_server.utils.logger import api_logger

router = APIRouter()


@router.post("/api/chat")
async def chat(
    request: ChatRequest,
    raw_request: Request,
    project: Project = Depends(get_project),  # noqa: B008
    chat_service: ChatService = Depends(get_chat_service),  # noqa: B008
):
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
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break

        if not user_message:
            api_logger.warning("No user message found in request")
            raise HTTPException(status_code=400, detail="No user message found")

        dialog_id = request.dialog_id or project.get_current_dialog_id()
        if not dialog_id:
            dialog_id = project.create_dialog(set_current=True)

        dialog_history = project.get_dialog_history(dialog_id)

        try:
            dialog_history.add_user_message(user_message)
        except Exception as e:
            api_logger.error("Failed to append user message", exception=e)

        recent_messages = []
        try:
            messages = dialog_history.get_messages(limit=20)
            recent_messages = messages
        except Exception as e:
            api_logger.error("Failed to load dialog history", exception=e)

        request.context = dict(request.context or {})
        request.context["dialog"] = {"id": dialog_id, "messages": recent_messages}

        if request.stream:
            api_logger.info("Returning SSE streaming response")
            response = stream_response(
                chat_service.stream_chat(
                    user_message, request.context, dialog_id, (project, dialog_id)
                ),
                dialog_id=dialog_id,
            )

            duration_ms = (time.time() - start_time) * 1000
            api_logger.request_log(
                "POST", "/api/chat", 200, duration_ms, streaming=True
            )
            return response
        else:
            api_logger.info("Processing non-streaming request")
            result = await chat_service.chat(
                query=user_message, context=request.context
            )

            try:
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

                dialog_history = project.get_dialog_history(dialog_id)

                if conversation:
                    existing_msg_count = len(recent_messages)
                    for msg in conversation[existing_msg_count + 1 :]:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            dialog_history.history.add_message(msg)  # type: ignore
                        elif hasattr(msg, "tool_call_id"):
                            dialog_history.history.add_message(msg)  # type: ignore

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
