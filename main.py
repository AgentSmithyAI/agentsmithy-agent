#!/usr/bin/env python3
"""Main entry point for AgentSmithy server.

Bootstraps a Uvicorn ASGI server for agentsmithy.api.server:app (shim over legacy
agentsmithy.api.server:app during migration).
Loads .env file from --workdir if present to populate environment variables.
Requires --workdir path and proper configuration (model and API key).
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
        help="IDE identifier (e.g., 'vscode', 'jetbrains', 'vim')",
    )
    parser.add_argument(
        "--log-format",
        choices=["pretty", "json"],
        help="Log format (pretty or json). Overrides config and LOG_FORMAT env var.",
    )
    parser.add_argument(
        "--log-colors",
        type=lambda x: x.lower() in ("true", "1", "yes", "on"),
        help="Enable colored logs (true/false). Overrides config and LOG_COLORS env var.",
    )
    # No --project: workdir is the project
    args, _ = parser.parse_known_args()

    # Set logging env vars from CLI flags before logger import
    # These override config and env vars, providing command-line precedence
    if args.log_format:
        os.environ["LOG_FORMAT"] = args.log_format
    if args.log_colors is not None:
        os.environ["LOG_COLORS"] = "true" if args.log_colors else "false"

    # Setup logging for startup (after argparse, so --help doesn't need logger)
    from agentsmithy.utils.logger import get_logger

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

    # Load .env file from workdir to populate environment variables for config
    from dotenv import load_dotenv

    env_file = workdir_path / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)
        startup_logger.debug("Loaded .env file", path=str(env_file))
    else:
        startup_logger.debug("No .env file found in workdir", path=str(env_file))

    # Initialize configuration manager
    from agentsmithy.config import (
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

    try:
        # Ensure hidden state directory exists FIRST
        # We need this to write status.json even on early failures
        try:
            # Initialize a workspace entity to own directory management
            from agentsmithy.core.project import set_workspace

            workspace = set_workspace(workdir_path)
            state_dir = workspace.root_state_dir
        except Exception as e:
            startup_logger.error("Failed to initialize workspace", error=str(e))
            sys.exit(1)

        # Workspace is now held in-process via set_workspace(); no env var needed

        # Delegate port selection and status.json management to project runtime
        from agentsmithy.core.project import get_current_project
        from agentsmithy.core.project_runtime import ensure_singleton_and_select_port
        from agentsmithy.core.status_manager import ServerStatus

        # Validate required settings (strict models + API key)
        # If validation fails, we'll mark server as stopped before exiting
        try:
            settings.validate_or_raise()
        except ValueError as e:
            startup_logger.error("Invalid configuration", error=str(e))
            # Write status as error (not stopped - this is a config failure)
            try:
                from agentsmithy.core.project_runtime import set_server_status

                set_server_status(
                    get_current_project(),
                    ServerStatus.ERROR,
                    error=f"Configuration validation failed: {str(e)}",
                )
            except Exception:
                # Best effort status update - if this fails, just exit
                # (project runtime may not be initialized yet)
                pass
            sys.exit(1)

        chosen_port = ensure_singleton_and_select_port(
            get_current_project(),
            base_port=settings.server_port,
            host=settings.server_host,
            max_probe=20,
        )
        # Status is now "starting" - server not ready yet
        # Update config with the chosen port
        if config_manager:
            asyncio.run(config_manager.set("server_port", chosen_port))

        # Treat workdir as the active project; inspect and save metadata if missing
        should_inspect = False
        project = None
        try:
            import asyncio

            from agentsmithy.agents.project_inspector_agent import (
                ProjectInspectorAgent,
            )
            from agentsmithy.core.project import get_current_project
            from agentsmithy.llm.providers.openai.provider import OpenAIProvider

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

        from agentsmithy.config import settings

        startup_logger.info(
            "Starting AgentSmithy Server",
            server_url=f"http://{settings.server_host}:{chosen_port}",
            docs_url=f"http://{settings.server_host}:{chosen_port}/docs",
            workdir=str(workdir_path),
            state_dir=str(state_dir),
        )

        # Use custom logging configuration for consistent output
        from agentsmithy.config.logging_config import get_logging_config

        LOGGING_CONFIG = get_logging_config()

        # Allow reload to be controlled via env (default False for prod)
        reload_enabled_env = os.getenv("SERVER_RELOAD", "false").lower()
        reload_enabled = reload_enabled_env in {"1", "true", "yes", "on"}

        # Custom Server subclass to set status to 'ready' after server starts listening
        class AgentSmithyServer(uvicorn.Server):
            async def startup(self, sockets=None):
                """Override startup to set status to 'ready' after server starts listening."""
                await super().startup(sockets=sockets)
                # Server is now listening, mark as ready
                from agentsmithy.core.project_runtime import set_server_status
                from agentsmithy.core.status_manager import ServerStatus

                set_server_status(get_current_project(), ServerStatus.READY)
                startup_logger.info("Server status updated to 'ready'")

        # Create custom server with lifespan enabled for proper startup/shutdown
        config = uvicorn.Config(
            "agentsmithy.api.server:app",
            host=settings.server_host,
            port=chosen_port,
            reload=reload_enabled,
            log_config=LOGGING_CONFIG,
            lifespan="on",
            timeout_graceful_shutdown=5,
        )
        server = AgentSmithyServer(config)
        # We'll manage signals ourselves; avoid double-handling in packaged builds
        try:
            # Uvicorn runtime attribute, not in type stubs - safe to set dynamically
            server.install_signal_handlers = False  # type: ignore[attr-defined]
        except Exception:
            # Attribute may not exist in some uvicorn versions - safe to ignore
            pass

        async def run_server():
            # Pass shutdown event and other state to the app before lifespan starts
            from agentsmithy.api.server import app

            app.state.shutdown_event = shutdown_event
            # Set IDE identifier as runtime parameter
            app.state.ide = args.ide
            # Pass config manager to app for lifespan
            app.state.config_manager = config_manager

            # Log runtime environment information
            from agentsmithy import __version__
            from agentsmithy.platforms import get_os_adapter

            adapter = get_os_adapter()
            os_ctx = adapter.os_context()
            shell = os_ctx.get("shell", "Unknown shell")
            if shell and "/" in shell:
                shell = shell.split("/")[-1]
            elif shell and "\\" in shell:
                shell = shell.split("\\")[-1]

            startup_logger.info(
                "Runtime environment",
                version=__version__,
                ide=args.ide or "unknown",
                system=os_ctx.get("system", "Unknown"),
                release=os_ctx.get("release", "unknown"),
                machine=os_ctx.get("machine", "unknown"),
                python=os_ctx.get("python", "unknown"),
                shell=shell,
            )

            # Optionally run project inspector in background (non-blocking)
            inspector_task = None
            if should_inspect:

                async def _run_inspector():
                    from agentsmithy.core.project_runtime import set_scan_status
                    from agentsmithy.core.status_manager import ScanStatus

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
                                ScanStatus.ERROR,
                                error=error_msg,
                            )
                            return

                        set_scan_status(project, ScanStatus.SCANNING, progress=0)

                        inspector = ProjectInspectorAgent(
                            OpenAIProvider(
                                model=inspector_model,
                                agent_name="project_inspector",
                            ),
                            None,
                        )
                        await inspector.inspect_and_save(project)

                        set_scan_status(project, ScanStatus.DONE, progress=100)

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
                        set_scan_status(project, ScanStatus.ERROR, error=error_msg)
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
                        set_scan_status(project, ScanStatus.ERROR, error=error_msg)

                inspector_task = asyncio.create_task(_run_inspector())
                app.state.inspector_task = inspector_task

            # Start uvicorn server (lifespan context manager handles startup/shutdown)
            serve_task = asyncio.create_task(server.serve())

            # Monitor shutdown event
            shutdown_task = asyncio.create_task(shutdown_event.wait())

            # Wait for either shutdown or server to complete
            done, _pending = await asyncio.wait(
                {shutdown_task, serve_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # If shutdown was triggered, stop the server
            if shutdown_task in done:
                startup_logger.info("Stopping server due to shutdown signal...")
                # Update status to stopping before actually stopping
                from agentsmithy.core.project_runtime import set_server_status
                from agentsmithy.core.status_manager import ServerStatus

                set_server_status(get_current_project(), ServerStatus.STOPPING)
                server.should_exit = True
                try:
                    await serve_task
                except Exception:
                    # Ignore cancellation/transport errors during shutdown
                    pass

            # Mark server as stopped after shutdown completes
            from agentsmithy.core.project_runtime import set_server_status
            from agentsmithy.core.status_manager import ServerStatus

            set_server_status(get_current_project(), ServerStatus.STOPPED)
            startup_logger.info("Server status updated to 'stopped'")

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
