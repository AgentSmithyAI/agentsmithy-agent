from __future__ import annotations

from .builtin.delete_file import DeleteFileTool
from .builtin.get_previous_result import GetPreviousResultTool
from .builtin.list_files import ListFilesTool
from .builtin.read_file import ReadFileTool
from .builtin.replace_in_file import ReplaceInFileTool
from .builtin.return_inspection import ReturnInspectionTool
from .builtin.run_command import RunCommandTool
from .builtin.search_files import SearchFilesTool
from .builtin.web_fetch import WebFetchTool
from .builtin.web_search import WebSearchTool
from .builtin.write_file import WriteFileTool
from .tool_manager import ToolManager


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
