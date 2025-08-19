#!/usr/bin/env python3
"""Main entry point for AgentSmithy server."""

import os
import sys
from argparse import ArgumentParser
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    # Setup basic logging for startup
    import logging

    # Try to import our structured logger, fallback to basic logging if not available
    try:
        from agentsmithy_server.utils.logger import StructuredLogger

        startup_logger = StructuredLogger("server.startup")
    except ImportError:
        # Fallback to basic colored logging
        logging.basicConfig(
            level=logging.INFO,
            format="\033[90m%(asctime)s\033[0m \033[32m%(levelname)-8s\033[0m \033[90m[%(name)s]\033[0m %(message)s",
            datefmt="%H:%M:%S",
        )
        startup_logger = logging.getLogger("server.startup")

    # Check if .env file exists
    if not os.path.exists(".env"):
        startup_logger.error(
            ".env file not found! Please create it from .env.example and add your OPENAI_API_KEY"
        )
        sys.exit(1)

    try:
        # Parse required --workdir before importing the server
        parser = ArgumentParser(description="Start AgentSmithy server")
        parser.add_argument(
            "--workdir",
            required=True,
            help="Absolute path to the working directory (agent state stored here)",
        )
        args, _ = parser.parse_known_args()

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

        # Expose to the process for later access
        os.environ["AGENTSMITHY_WORKDIR"] = str(workdir_path)

        import uvicorn

        from agentsmithy_server.api.server import settings

        startup_logger.info(
            "Starting AgentSmithy Server",
            server_url=f"http://{settings.server_host}:{settings.server_port}",
            docs_url=f"http://{settings.server_host}:{settings.server_port}/docs",
            workdir=str(workdir_path),
            state_dir=str(state_dir),
        )

        # Use custom logging configuration for consistent JSON output
        from agentsmithy_server.config import LOGGING_CONFIG

        uvicorn.run(
            "agentsmithy_server.api.server:app",
            host=settings.server_host,
            port=settings.server_port,
            reload=True,
            log_config=LOGGING_CONFIG,
            env_file=".env",
        )
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
