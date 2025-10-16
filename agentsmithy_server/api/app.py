from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agentsmithy_server.api.routes.chat import router as chat_router
from agentsmithy_server.api.routes.dialogs import router as dialogs_router
from agentsmithy_server.api.routes.health import router as health_router
from agentsmithy_server.api.routes.history import router as history_router
from agentsmithy_server.api.routes.meta import router as meta_router
from agentsmithy_server.api.routes.tool_results import router as tool_results_router
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

        # Start config watcher in the main event loop
        if hasattr(app.state, "config_manager"):
            # Register callback to invalidate orchestrator on config changes
            from agentsmithy_server.api.deps import get_chat_service

            def on_config_change(new_config):
                api_logger.info(
                    "Configuration changed, invalidating cached components",
                    changed_keys=list(new_config.keys()),
                )
                # Invalidate orchestrator so it picks up new config on next request
                chat_service = get_chat_service()
                chat_service.invalidate_orchestrator()

            app.state.config_manager.register_change_callback(on_config_change)
            await app.state.config_manager.start_watching()
            api_logger.info("Config file watcher started with change callback")
    except Exception as e:
        api_logger.error("Startup initialization failed", exc_info=True, error=str(e))

    yield

    # Shutdown: cleanup active streams and resources
    try:
        api_logger.info("Starting shutdown cleanup")
        from agentsmithy_server.api.deps import dispose_db_engine, get_chat_service

        # Stop config watcher
        if hasattr(app.state, "config_manager"):
            await app.state.config_manager.stop_watching()
            api_logger.info("Config file watcher stopped")

        chat_service = get_chat_service()
        await chat_service.shutdown()
        dispose_db_engine()
        api_logger.info("Chat service shutdown completed")
    except Exception as e:
        api_logger.error("Shutdown cleanup failed", exc_info=True, error=str(e))


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

    # Force-create DB engine early to warm up (optional; safe to remove)
    try:
        from agentsmithy_server.api.deps import get_db_engine

        _ = get_db_engine()
    except Exception:
        pass

    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(dialogs_router)
    app.include_router(history_router)
    app.include_router(meta_router)
    app.include_router(tool_results_router)

    # Basic error handler example
    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        # Placeholder for request_id; could be a ULID
        response = await call_next(request)
        response.headers.setdefault("x-request-id", "agentsmithy")
        return response

    return app
