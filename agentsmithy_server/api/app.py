from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agentsmithy_server.api.routes.chat import router as chat_router
from agentsmithy_server.api.routes.dialogs import router as dialogs_router
from agentsmithy_server.api.routes.health import router as health_router
from agentsmithy_server.api.routes.meta import router as meta_router
from agentsmithy_server.core.project import get_current_project
from agentsmithy_server.utils.logger import api_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure dialogs state and default dialog
    try:
        project = get_current_project()
        project.ensure_dialogs_dir()
        index = project.load_dialogs_index()
        dialogs = index.get("dialogs") or []
        if not dialogs:
            project.create_dialog(title="default", set_current=True)
            
        # Get shutdown event from app state if available
        if hasattr(app.state, "shutdown_event"):
            from agentsmithy_server.api.deps import set_shutdown_event
            set_shutdown_event(app.state.shutdown_event)
            api_logger.info("Shutdown event registered with chat service")
    except Exception as e:
        api_logger.error("Dialog state init failed", exception=e)

    yield

    # Shutdown: cleanup active streams and resources
    try:
        api_logger.info("Starting shutdown cleanup")
        from agentsmithy_server.api.deps import get_chat_service
        chat_service = get_chat_service()
        await chat_service.shutdown()
        api_logger.info("Chat service shutdown completed")
    except Exception as e:
        api_logger.error("Shutdown cleanup failed", exception=e)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentSmithy Server",
        description="AI agent server similar to Cursor, powered by LangGraph",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(dialogs_router)
    app.include_router(meta_router)
    
    # Temporary test endpoint for shutdown testing
    @app.get("/test/sse")
    async def test_sse():
        """Test SSE endpoint for shutdown testing."""
        from agentsmithy_server.api.sse import stream_response
        from agentsmithy_server.api.sse_protocol import EventFactory as SSEEventFactory
        
        async def generate_test_events():
            """Generate test events continuously."""
            import asyncio
            try:
                for i in range(100):
                    yield SSEEventFactory.chat(f"Test event {i}").to_sse()
                    await asyncio.sleep(0.05)  # 50ms between events
            except asyncio.CancelledError:
                api_logger.info("Test SSE stream cancelled")
                raise
            finally:
                yield SSEEventFactory.done().to_sse()
        
        return stream_response(generate_test_events())

    # Basic error handler example
    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        # Placeholder for request_id; could be a ULID
        response = await call_next(request)
        response.headers.setdefault("x-request-id", "agentsmithy")
        return response

    return app
