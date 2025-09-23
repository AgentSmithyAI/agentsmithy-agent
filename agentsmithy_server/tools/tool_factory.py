from __future__ import annotations

from .delete_file import DeleteFileTool
from .get_previous_result import GetPreviousResultTool
from .list_files import ListFilesTool
from .read_file import ReadFileTool
from .replace_in_file import ReplaceInFileTool
from .return_inspection import ReturnInspectionTool
from .run_command import RunCommandTool
from .search_files import SearchFilesTool
from .tool_manager import ToolManager
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .write_file import WriteFileTool


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
        manager.register(ReturnInspectionTool())
        manager.register(DeleteFileTool())
        manager.register(RunCommandTool())
        manager.register(WebFetchTool())
        manager.register(WebSearchTool())
        manager.register(GetPreviousResultTool())
        return manager
