"""SSE adapter utilities.

Provides `stream_response` to wrap async generators of dicts into EventSourceResponse,
and a simple heartbeat facility (to be expanded later).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import EventSourceResponse


def stream_response(
    event_stream: AsyncIterator[dict[str, Any]], dialog_id: str | None = None
) -> EventSourceResponse:
    async def guarded_stream() -> AsyncIterator[dict[str, Any]]:
        import json as _json

        from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory
        from agentsmithy_server.utils.logger import api_logger

        done_sent = False
        try:
            async for event in event_stream:
                try:
                    payload = _json.loads(event.get("data", "") or "{}")
                    if payload.get("type") == "done" or payload.get("done"):
                        done_sent = True
                except Exception:
                    # Ignore parse errors; pass through event as-is
                    pass
                yield event
        except Exception as e:
            api_logger.error("SSE pipeline crashed", exception=e)
            # Always send error, then done (if not yet sent)
            yield SSEEventFactory.error(message=str(e), dialog_id=dialog_id).to_sse()
            if not done_sent:
                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
            return
        finally:
            if not done_sent:
                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()

    return EventSourceResponse(
        guarded_stream(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
