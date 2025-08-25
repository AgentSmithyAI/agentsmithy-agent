"""FastAPI server for AgentSmithy.

This module is a thin ASGI entrypoint that delegates to create_app().
"""

from fastapi import FastAPI


try:
    from agentsmithy_server.api.app import create_app as _create_app

    app: FastAPI = _create_app()
except Exception:  # pragma: no cover - legacy fallback
    app = FastAPI(title="AgentSmithy Server")
