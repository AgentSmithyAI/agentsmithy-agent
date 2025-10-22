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
        import asyncio
        import json as _json

        from agentsmithy.api.sse_protocol import EventFactory as SSEEventFactory
        from agentsmithy.utils.logger import api_logger

        done_sent = False
        shutdown = False

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
        except GeneratorExit:
            # Handle generator exit - this is normal during shutdown
            api_logger.info("SSE generator closed")
            shutdown = True
            # Don't yield anything here - just clean up and exit
            return
        except asyncio.CancelledError:
            # Handle graceful shutdown
            api_logger.info("SSE stream cancelled during shutdown")
            shutdown = True
            if not done_sent:
                # Try to send done event before re-raising
                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                done_sent = True
            raise
        except ValueError as e:
            # Configuration errors (e.g., missing model) - log without full traceback
            api_logger.error(
                "Configuration error",
                error_type="ValueError",
                error=str(e),
            )
            # Send error to client
            yield SSEEventFactory.error(message=str(e), dialog_id=dialog_id).to_sse()
            if not done_sent:
                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                done_sent = True
            return
        except Exception as e:
            api_logger.error("SSE pipeline crashed", exc_info=True, error=str(e))
            # Always send error, then done (if not yet sent)
            yield SSEEventFactory.error(message=str(e), dialog_id=dialog_id).to_sse()
            if not done_sent:
                yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()
                done_sent = True
            return

        # Only send done if we completed normally (not shutdown)
        if not done_sent and not shutdown:
            yield SSEEventFactory.done(dialog_id=dialog_id).to_sse()

    return EventSourceResponse(
        guarded_stream(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
