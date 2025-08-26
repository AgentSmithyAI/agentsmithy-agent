from __future__ import annotations

from .delete_file import DeleteFileTool
from .list_files import ListFilesTool
from .patch_file import PatchFileTool
from .read_file import ReadFileTool
from .replace_in_file import ReplaceInFileTool
from .return_inspection import ReturnInspectionTool
from .search_files import SearchFilesTool
from .tool_manager import ToolManager
from .write_file import WriteFileTool


class ToolFactory:
    """Factory for creating standard tool sets and tool managers."""

    @staticmethod
    def create_tool_manager() -> ToolManager:
        manager = ToolManager()
        # Register default tools (Cline-style set)
        manager.register(ReadFileTool())
        manager.register(WriteFileTool())
        manager.register(ReplaceInFileTool())  # Now includes enhanced features
        manager.register(ListFilesTool())
        manager.register(SearchFilesTool())
        manager.register(PatchFileTool())  # keep for unified diff workflow
        manager.register(ReturnInspectionTool())
        manager.register(DeleteFileTool())
        return manager
