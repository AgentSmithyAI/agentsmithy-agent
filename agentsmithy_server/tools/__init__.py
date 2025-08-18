"""Tools framework for AgentSmithy server.

Provides a simple plan/act execution model via LLM + tools. This module is
server-oriented (no IDE plugin coupling) and streams structured events
compatible with our SSE protocol (e.g., diff events).
"""

from .base_tool import BaseTool
from .patch_file import PatchFileTool
from .tool_manager import ToolManager
from .tool_executor import ToolExecutor
from .tool_factory import ToolFactory

__all__ = [
    "BaseTool",
    "PatchFileTool",
    "ToolManager",
    "ToolExecutor",
    "ToolFactory",
]



