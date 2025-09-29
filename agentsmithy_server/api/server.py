"""FastAPI server for AgentSmithy.

This module is a thin ASGI entrypoint that delegates to create_app().
"""

from agentsmithy_server.api.app import create_app

app = create_app()
