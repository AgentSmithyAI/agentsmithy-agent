"""Tools framework for AgentSmithy server.

Provides a simple plan/act execution model via LLM + tools. This module is
server-oriented (no IDE plugin coupling) and streams structured events
compatible with our SSE protocol (e.g., diff events).
"""

from .base_tool import BaseTool
from .delete_file import DeleteFileTool
from .run_command import RunCommandTool
from .tool_executor import ToolExecutor
from .tool_factory import ToolFactory
from .tool_manager import ToolManager

__all__ = [
    "BaseTool",
    "ToolManager",
    "ToolExecutor",
    "ToolFactory",
    "DeleteFileTool",
    "RunCommandTool",
]
