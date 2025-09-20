from __future__ import annotations

from .delete_file import DeleteFileTool
from .list_files import ListFilesTool
from .patch_file import PatchFileTool
from .read_file import ReadFileTool
from .replace_in_file import ReplaceInFileTool
from .return_inspection import ReturnInspectionTool
from .run_command import RunCommandTool
from .search_files import SearchFilesTool
from .tool_manager import ToolManager
from .write_file import WriteFileTool
from .web_fetch import WebFetchTool


class ToolFactory:
    """Factory for creating standard tool sets and tool managers."""

    @staticmethod
    def create_tool_manager() -> ToolManager:
        manager = ToolManager()
        # Register default tools
        manager.register(ReadFileTool())
        manager.register(WriteFileTool())
        manager.register(ReplaceInFileTool())  # Now includes enhanced features
        manager.register(ListFilesTool())
        manager.register(SearchFilesTool())
        manager.register(PatchFileTool())  # keep for unified diff workflow
        manager.register(ReturnInspectionTool())
        manager.register(DeleteFileTool())
        manager.register(RunCommandTool())
        manager.register(WebFetchTool())
        return manager
