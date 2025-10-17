#!/usr/bin/env python3
"""Main entry point for AgentSmithy server.

Bootstraps a Uvicorn ASGI server for agentsmithy_server.api.server:app.
Requires a .env (DEFAULT_MODEL and OPENAI_API_KEY) and a --workdir path.
"""

import asyncio
import os
import signal
import sys
from argparse import ArgumentParser
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()

if __name__ == "__main__":
    # Parse arguments FIRST (before any config validation) so --help works always
    parser = ArgumentParser(description="Start AgentSmithy server")
    parser.add_argument(
        "--workdir",
        required=True,
        help="Absolute path to the working directory (agent state stored here)",
    )
    parser.add_argument(
        "--ide",
        required=False,
        help="IDE identifier (e.g., 'vscode', 'cursor', 'jetbrains')",
    )
    # No --project: workdir is the project
    args, _ = parser.parse_known_args()

    # Setup logging for startup (after argparse, so --help doesn't need logger)
    from agentsmithy_server.utils.logger import get_logger

    startup_logger = get_logger("server.startup")

    # Signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        sig_name = signal.Signals(signum).name
        startup_logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Validate and change to workdir early (before .env and settings loading)
    workdir_path = Path(args.workdir).expanduser().resolve()
    if not workdir_path.exists():
        startup_logger.error("--workdir does not exist", path=str(workdir_path))
        sys.exit(1)
    if not workdir_path.is_dir():
        startup_logger.error("--workdir is not a directory", path=str(workdir_path))
        sys.exit(1)

    # Change working directory to workdir so relative paths work correctly
    os.chdir(workdir_path)
    startup_logger.debug("Changed working directory", workdir=str(workdir_path))

    # Initialize configuration manager
    from agentsmithy_server.config import (
        create_config_manager,
        get_default_config,
        settings,
    )

    try:
        # Create .agentsmithy directory if it doesn't exist
        config_dir = workdir_path / ".agentsmithy"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create and initialize config manager
        config_manager = create_config_manager(
            config_dir, defaults=get_default_config()
        )

        # Run async initialization (watch will start later in manual startup to use correct event loop)
        async def init_config():
            await config_manager.initialize()

        asyncio.run(init_config())

        # Update global settings instance to use config manager
        settings._config_manager = config_manager

        startup_logger.info(
            "Configuration initialized",
            config_file=str(config_dir / "config.json"),
        )
    except Exception as e:
        startup_logger.error("Failed to initialize configuration", error=str(e))
        sys.exit(1)

    # Validate required settings (strict models + API key)
    try:
        settings.validate_or_raise()
    except ValueError as e:
        startup_logger.error("Invalid configuration", error=str(e))
        sys.exit(1)

    try:
        # Ensure hidden state directory exists
        try:
            # Initialize a workspace entity to own directory management
            from agentsmithy_server.core.project import set_workspace

            workspace = set_workspace(workdir_path)
            state_dir = workspace.root_state_dir
        except Exception as e:
            startup_logger.error("Failed to initialize workspace", error=str(e))
            sys.exit(1)

        # Workspace is now held in-process via set_workspace(); no env var needed

        # Delegate port selection and status.json management to project runtime
        from agentsmithy_server.core.project import get_current_project
        from agentsmithy_server.core.project_runtime import (
            ensure_singleton_and_select_port,
        )

        chosen_port = ensure_singleton_and_select_port(
            get_current_project(),
            base_port=settings.server_port,
            host=settings.server_host,
            max_probe=20,
        )
        # Update config with the chosen port
        if config_manager:
            asyncio.run(config_manager.set("server_port", chosen_port))

        # Treat workdir as the active project; inspect and save metadata if missing
        should_inspect = False
        project = None
        try:
            import asyncio

            from agentsmithy_server.agents.project_inspector_agent import (
                ProjectInspectorAgent,
            )
            from agentsmithy_server.core.project import get_current_project
            from agentsmithy_server.llm.providers.openai.provider import OpenAIProvider

            project = get_current_project()
            project.root.mkdir(parents=True, exist_ok=True)
            project.ensure_state_dir()
            project.ensure_gitignore_entry()  # Ensure .agentsmithy is in .gitignore
            should_inspect = not project.has_metadata()
            if should_inspect:
                startup_logger.info(
                    "Scheduling background project inspection",
                    project=project.name,
                )
        except Exception as e:
            # Log full exception details for diagnostics
            import traceback as _tb

            startup_logger.error(
                "Project inspection failed",
                error=str(e),
                traceback="".join(_tb.format_exception(type(e), e, e.__traceback__)),
            )

        import uvicorn

        from agentsmithy_server.config import settings

        startup_logger.info(
            "Starting AgentSmithy Server",
            server_url=f"http://{settings.server_host}:{chosen_port}",
            docs_url=f"http://{settings.server_host}:{chosen_port}/docs",
            workdir=str(workdir_path),
            state_dir=str(state_dir),
        )

        # Use custom logging configuration for consistent JSON output
        from agentsmithy_server.config import LOGGING_CONFIG

        # Allow reload to be controlled via env (default False for prod)
        reload_enabled_env = os.getenv("SERVER_RELOAD", "false").lower()
        reload_enabled = reload_enabled_env in {"1", "true", "yes", "on"}

        # Create custom server to pass shutdown event
        # Disable ASGI lifespan to avoid starlette lifespan CancelledError on shutdown
        # Manual startup/shutdown hooks are used instead (see below)
        config = uvicorn.Config(
            "agentsmithy_server.api.server:app",
            host=settings.server_host,
            port=chosen_port,
            reload=reload_enabled,
            log_config=LOGGING_CONFIG,
            lifespan="off",
            timeout_graceful_shutdown=5,
        )
        server = uvicorn.Server(config)
        # We'll manage signals ourselves; avoid double-handling in packaged builds
        try:
            server.install_signal_handlers = False  # type: ignore[attr-defined]
        except Exception:
            pass

        async def run_server():
            # Pass shutdown event to the app
            from agentsmithy_server.api.server import app

            app.state.shutdown_event = shutdown_event
            # Set IDE identifier as runtime parameter
            app.state.ide = args.ide
            # Pass config manager to app for lifespan
            app.state.config_manager = config_manager

            # Log runtime environment information
            from agentsmithy_server.platforms import get_os_adapter

            adapter = get_os_adapter()
            os_ctx = adapter.os_context()
            shell = os_ctx.get("shell", "Unknown shell")
            if shell and "/" in shell:
                shell = shell.split("/")[-1]
            elif shell and "\\" in shell:
                shell = shell.split("\\")[-1]

            startup_logger.info(
                "Runtime environment",
                system=os_ctx.get("system", "Unknown"),
                release=os_ctx.get("release", "unknown"),
                machine=os_ctx.get("machine", "unknown"),
                python=os_ctx.get("python", "unknown"),
                shell=shell,
                ide=args.ide or "unknown",
            )

            # Optionally run project inspector in background (non-blocking)
            inspector_task = None
            if should_inspect:

                async def _run_inspector():
                    from agentsmithy_server.core.project_runtime import set_scan_status

                    try:
                        # Check if model is configured
                        inspector_model = (
                            os.getenv("AGENTSMITHY_INSPECTOR_MODEL") or settings.model
                        )
                        if not inspector_model:
                            error_msg = (
                                "Cannot run project inspection: LLM model not configured. "
                                "Please set 'model' in .agentsmithy/config.json or "
                                "AGENTSMITHY_INSPECTOR_MODEL environment variable."
                            )
                            startup_logger.error(
                                "Project inspection skipped",
                                reason="model_not_configured",
                                error=error_msg,
                            )
                            set_scan_status(
                                project,
                                status="error",
                                error=error_msg,
                            )
                            return

                        set_scan_status(project, status="scanning", progress=0)

                        inspector = ProjectInspectorAgent(
                            OpenAIProvider(
                                model=inspector_model,
                                agent_name="project_inspector",
                            ),
                            None,
                        )
                        await inspector.inspect_and_save(project)

                        set_scan_status(project, status="done", progress=100)

                        startup_logger.info(
                            "Project analyzed by inspector agent and metadata saved",
                            project=project.name,
                            model=inspector_model,
                        )
                    except ValueError as e:
                        # Model/config related errors
                        error_msg = f"Configuration error: {str(e)}"
                        startup_logger.error(
                            "Project inspection failed",
                            error_type="configuration",
                            error=error_msg,
                        )
                        set_scan_status(project, status="error", error=error_msg)
                    except Exception as e:
                        import traceback as _tb

                        error_msg = f"{type(e).__name__}: {str(e)}"
                        startup_logger.error(
                            "Background project inspection failed",
                            error=str(e),
                            traceback="".join(
                                _tb.format_exception(type(e), e, e.__traceback__)
                            ),
                        )
                        set_scan_status(project, status="error", error=error_msg)

                inspector_task = asyncio.create_task(_run_inspector())
                app.state.inspector_task = inspector_task

            # --- Manual startup (since lifespan is off) ---
            try:
                # Ensure dialogs state and default dialog
                from agentsmithy_server.api.deps import (
                    get_chat_service,
                    set_shutdown_event,
                )
                from agentsmithy_server.core.project import get_current_project

                project_obj = get_current_project()
                project_obj.ensure_dialogs_dir()
                index = project_obj.load_dialogs_index()
                dialogs = index.get("dialogs") or []
                if not dialogs:
                    project_obj.create_dialog(title="default", set_current=True)

                # Propagate shutdown event to chat service
                set_shutdown_event(shutdown_event)

                # Start config watcher and register change callback
                if hasattr(app.state, "config_manager") and app.state.config_manager:

                    def on_config_change(new_config):
                        # Invalidate orchestrator on config change
                        chat_service_local = get_chat_service()
                        chat_service_local.invalidate_orchestrator()

                    app.state.config_manager.register_change_callback(on_config_change)
                    await app.state.config_manager.start_watching()
                    startup_logger.info(
                        "Config file watcher started with change callback"
                    )
            except Exception as e:
                startup_logger.error("Startup initialization failed", error=str(e))

            # Monitor shutdown event and uvicorn serve()
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            serve_task = asyncio.create_task(server.serve())

            # Wait for either shutdown or server to complete
            done, _pending = await asyncio.wait(
                {shutdown_task, serve_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # If shutdown was triggered, stop the server
            if shutdown_task in done:
                startup_logger.info("Stopping server due to shutdown signal...")
                server.should_exit = True
                try:
                    await serve_task
                except Exception:
                    # Ignore cancellation/transport errors during shutdown
                    pass

            # --- Manual shutdown (since lifespan is off) ---
            try:
                from agentsmithy_server.api.deps import (
                    dispose_db_engine,
                    get_chat_service,
                )

                # Stop config watcher
                if hasattr(app.state, "config_manager") and app.state.config_manager:
                    try:
                        await app.state.config_manager.stop_watching()
                        startup_logger.info("Config file watcher stopped")
                    except Exception:
                        pass

                chat_service = get_chat_service()
                try:
                    await chat_service.shutdown()
                except Exception:
                    pass

                dispose_db_engine()
                startup_logger.info("Chat service shutdown completed")
            except Exception as e:
                startup_logger.error("Shutdown cleanup failed", error=str(e))

        # Run server with asyncio
        asyncio.run(run_server())
    except ImportError as e:
        startup_logger.error(
            "Error importing required modules",
            error=str(e),
            hint="Run: pip install -r requirements.txt",
        )
        sys.exit(1)
    except Exception as e:
        startup_logger.error("Error starting server", error=str(e))
        sys.exit(1)
