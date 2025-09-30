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

    # Check if .env file exists (after argparse, so --help doesn't need .env)
    if not os.path.exists(".env"):
        startup_logger.error(
            ".env file not found! Please create it from .env.example and add your OPENAI_API_KEY"
        )
        sys.exit(1)

    # Validate required settings
    from agentsmithy_server.config import settings

    if not settings.default_model:
        startup_logger.error(
            "DEFAULT_MODEL not set in .env file! Please specify the LLM model to use."
        )
        sys.exit(1)

    try:

        workdir_path = Path(args.workdir).expanduser().resolve()
        if not workdir_path.exists():
            startup_logger.error("--workdir does not exist", path=str(workdir_path))
            sys.exit(1)
        if not workdir_path.is_dir():
            startup_logger.error("--workdir is not a directory", path=str(workdir_path))
            sys.exit(1)

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
            base_port=int(os.getenv("SERVER_PORT", "11434")),
            host=settings.server_host,
            max_probe=20,
        )
        # Keep settings in sync with the chosen port for logging/uvicorn
        try:
            settings.server_port = chosen_port
        except Exception:
            pass

        # Treat workdir as the active project; inspect and save metadata if missing
        should_inspect = False
        project = None
        try:
            import asyncio

            from agentsmithy_server.agents.project_inspector_agent import (
                ProjectInspectorAgent,
            )
            from agentsmithy_server.core import LLMFactory
            from agentsmithy_server.core.project import get_current_project

            project = get_current_project()
            project.root.mkdir(parents=True, exist_ok=True)
            project.ensure_state_dir()
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
        config = uvicorn.Config(
            "agentsmithy_server.api.server:app",
            host=settings.server_host,
            port=chosen_port,
            reload=reload_enabled,
            log_config=LOGGING_CONFIG,
            env_file=".env",
        )
        server = uvicorn.Server(config)

        async def run_server():
            # Pass shutdown event to the app
            from agentsmithy_server.api.server import app

            app.state.shutdown_event = shutdown_event

            # Optionally run project inspector in background (non-blocking)
            inspector_task = None
            if should_inspect:

                async def _run_inspector():
                    try:
                        inspector = ProjectInspectorAgent(
                            LLMFactory.create(
                                "openai",
                                model=os.getenv("AGENTSMITHY_INSPECTOR_MODEL"),
                                agent_name="project_inspector",
                            ),
                            None,
                        )
                        await inspector.inspect_and_save(project)
                        startup_logger.info(
                            "Project analyzed by inspector agent and metadata saved",
                            project=project.name,
                        )
                    except Exception as e:
                        import traceback as _tb

                        startup_logger.error(
                            "Background project inspection failed",
                            error=str(e),
                            traceback="".join(
                                _tb.format_exception(type(e), e, e.__traceback__)
                            ),
                        )

                inspector_task = asyncio.create_task(_run_inspector())
                app.state.inspector_task = inspector_task

            # Monitor shutdown event
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            serve_task = asyncio.create_task(server.serve())

            # Wait for either shutdown or server to complete
            done, pending = await asyncio.wait(
                {shutdown_task, serve_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # If shutdown was triggered, stop the server
            if shutdown_task in done:
                startup_logger.info("Stopping server due to shutdown signal...")
                server.should_exit = True
                await serve_task

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
