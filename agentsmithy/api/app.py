from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agentsmithy import __version__
from agentsmithy.api.routes.chat import router as chat_router
from agentsmithy.api.routes.checkpoints import router as checkpoints_router
from agentsmithy.api.routes.config import router as config_router
from agentsmithy.api.routes.dialogs import router as dialogs_router
from agentsmithy.api.routes.health import router as health_router
from agentsmithy.api.routes.history import router as history_router
from agentsmithy.api.routes.tool_results import router as tool_results_router
from agentsmithy.core.project import get_current_project
from agentsmithy.utils.logger import api_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure dialogs state and default dialog
    try:
        project = get_current_project()
        project.ensure_dialogs_dir()
        index = project.load_dialogs_index()
        dialogs = index.get("dialogs") or []
        if not dialogs:
            project.create_dialog(title=None, set_current=True)

        # Get shutdown event from app state if available
        if hasattr(app.state, "shutdown_event"):
            from agentsmithy.api.deps import set_shutdown_event

            set_shutdown_event(app.state.shutdown_event)
            api_logger.info("Shutdown event registered with chat service")

        # Start config watcher in the main event loop
        if hasattr(app.state, "config_manager"):
            # Register callback to invalidate orchestrator on config changes
            from agentsmithy.api.deps import get_chat_service

            def on_config_change(new_config):
                api_logger.info(
                    "Configuration changed, invalidating cached components",
                    changed_keys=list(new_config.keys()),
                )
                # Invalidate orchestrator so it picks up new config on next request
                chat_service = get_chat_service()
                chat_service.invalidate_orchestrator()

                # Update config validity in status.json
                from agentsmithy.config import settings
                from agentsmithy.core.project_runtime import read_status, write_status

                try:
                    project = get_current_project()
                    if not project:
                        return
                    status_doc = read_status(project)
                    config_valid, config_errors = settings.validation_status()
                    status_doc["config_valid"] = config_valid
                    if config_errors:
                        status_doc["config_errors"] = config_errors
                    else:
                        status_doc.pop("config_errors", None)
                    write_status(project, status_doc)
                    api_logger.info(
                        "Updated config validity in status.json",
                        config_valid=config_valid,
                    )
                except Exception as e:
                    api_logger.warning(
                        "Failed to update config validity in status.json", error=str(e)
                    )

            app.state.config_manager.register_change_callback(on_config_change)
            await app.state.config_manager.start_watching()
            api_logger.info("Config file watcher started with change callback")
    except Exception as e:
        api_logger.error("Startup initialization failed", exc_info=True, error=str(e))
        # Mark server as error on startup failure
        from agentsmithy.core.project_runtime import set_server_status
        from agentsmithy.core.status_manager import ServerStatus

        set_server_status(
            get_current_project(), ServerStatus.ERROR, error=f"Startup failed: {str(e)}"
        )
        raise

    yield

    # Shutdown: cleanup active streams and resources
    try:
        api_logger.info("Starting shutdown cleanup")
        from agentsmithy.api.deps import dispose_db_engine, get_chat_service
        from agentsmithy.core.background_tasks import get_background_manager

        # Stop config watcher
        if hasattr(app.state, "config_manager"):
            try:
                await app.state.config_manager.stop_watching()
                api_logger.info("Config file watcher stopped")
            except asyncio.CancelledError:
                # Shutdown was cancelled, but continue with other cleanup
                api_logger.debug("Config watcher stop cancelled, continuing cleanup")

        # Shutdown background tasks (RAG reindexing, etc.)
        bg_manager = get_background_manager()
        try:
            await bg_manager.shutdown(timeout=10.0)
        except asyncio.CancelledError:
            api_logger.debug("Background tasks shutdown cancelled, continuing cleanup")

        # Shutdown chat service
        chat_service = get_chat_service()
        try:
            await chat_service.shutdown()
        except asyncio.CancelledError:
            # Shutdown was cancelled, but continue with other cleanup
            api_logger.debug("Chat service shutdown cancelled, continuing cleanup")

        # DB engine disposal is synchronous, always safe
        dispose_db_engine()
        api_logger.info("Shutdown completed")
    except Exception as e:
        api_logger.error("Shutdown cleanup failed", exc_info=True, error=str(e))


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentSmithy Server",
        description="AI coding assistant server with LangGraph orchestration and RAG-powered context",
        version=__version__,
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
        from agentsmithy.api.deps import get_db_engine

        _ = get_db_engine()
    except Exception:
        # DB engine creation is optional warmup - safe to skip if it fails
        pass

    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(dialogs_router)
    app.include_router(history_router)
    app.include_router(tool_results_router)
    app.include_router(checkpoints_router)
    app.include_router(config_router)

    # Basic error handler example
    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        # Placeholder for request_id; could be a ULID
        response = await call_next(request)
        response.headers.setdefault("x-request-id", "agentsmithy")
        return response

    return app
