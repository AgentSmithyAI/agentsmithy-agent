from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from agentsmithy.api.deps import get_chat_service, get_project
from agentsmithy.api.schemas import ChatRequest, ChatResponse
from agentsmithy.api.sse import stream_response
from agentsmithy.core.project import Project
from agentsmithy.services.chat_service import ChatService
from agentsmithy.utils.logger import api_logger, request_log

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
            dialog_id = project.create_dialog(title=None, set_current=True)

        request.context = dict(request.context or {})
        # Add IDE runtime parameter to context
        if hasattr(raw_request.app.state, "ide"):
            request.context["ide"] = raw_request.app.state.ide

        if request.stream:
            api_logger.info("Returning SSE streaming response")
            response = stream_response(
                chat_service.stream_chat(
                    user_message, request.context, dialog_id, (project, dialog_id)
                ),
                dialog_id=dialog_id,
            )

            duration_ms = (time.time() - start_time) * 1000
            request_log(
                api_logger, "POST", "/api/chat", 200, duration_ms, streaming=True
            )
            return response
        else:
            api_logger.info("Processing non-streaming request")
            result = await chat_service.chat(
                query=user_message,
                context=request.context,
                dialog_id=dialog_id,
                project=project,
            )

            json_response = ChatResponse(
                content=result["response"], done=True, metadata=result["metadata"]
            )

            duration_ms = (time.time() - start_time) * 1000
            request_log(
                api_logger,
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
        api_logger.error(
            "Chat request failed", exc_info=True, error=str(e), duration_ms=duration_ms
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
