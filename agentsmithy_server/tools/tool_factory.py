from __future__ import annotations

from .patch_file import PatchFileTool
from .tool_manager import ToolManager


class ToolFactory:
    """Factory for creating standard tool sets and tool managers."""

    @staticmethod
    def create_tool_manager() -> ToolManager:
        manager = ToolManager()
        # Register default tools
        manager.register(PatchFileTool())
        return manager



