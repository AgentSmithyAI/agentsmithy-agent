"""Tools framework for AgentSmithy server.

Provides a simple plan/act execution model via LLM + tools. This module is
server-oriented (no IDE plugin coupling) and streams structured events
compatible with our SSE protocol (e.g., diff events).
"""

from .base_tool import BaseTool
from .build_registry import build_registry

# Re-export commonly used tools from builtin package
from .builtin.delete_file import DeleteFileTool
from .builtin.run_command import RunCommandTool

# Re-export summary registration helpers for convenience
from .registry import (
    ToolRegistry,
    register_summaries,
    register_summary,
    register_summary_for,
)
from .tool_executor import ToolExecutor

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolExecutor",
    "build_registry",
    "DeleteFileTool",
    "RunCommandTool",
    "register_summary",
    "register_summaries",
    "register_summary_for",
]
