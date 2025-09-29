"""Builtin tool package.

Static export of tool classes for reliable bundling and registration.

Why static: Dynamic discovery via pkgutil/importlib doesn't work in
PyInstaller onefile binaries because packages are not visible as FS dirs.
Keeping an explicit list ensures tools are included and registered.
"""

from __future__ import annotations

from agentsmithy_server.tools.builtin.delete_file import DeleteFileTool
from agentsmithy_server.tools.builtin.get_previous_result import (
    GetPreviousResultTool,
)
from agentsmithy_server.tools.builtin.list_files import ListFilesTool
from agentsmithy_server.tools.builtin.read_file import ReadFileTool
from agentsmithy_server.tools.builtin.replace_in_file import ReplaceInFileTool
from agentsmithy_server.tools.builtin.return_inspection import (
    ReturnInspectionTool,
)
from agentsmithy_server.tools.builtin.run_command import RunCommandTool
from agentsmithy_server.tools.builtin.search_files import SearchFilesTool
from agentsmithy_server.tools.builtin.web_fetch import WebFetchTool
from agentsmithy_server.tools.builtin.web_search import WebSearchTool
from agentsmithy_server.tools.builtin.write_file import WriteFileTool

TOOL_CLASSES = [
    DeleteFileTool,
    GetPreviousResultTool,
    ListFilesTool,
    ReadFileTool,
    ReplaceInFileTool,
    ReturnInspectionTool,
    RunCommandTool,
    SearchFilesTool,
    WebFetchTool,
    WebSearchTool,
    WriteFileTool,
]

__all__ = [
    "TOOL_CLASSES",
    "DeleteFileTool",
    "GetPreviousResultTool",
    "ListFilesTool",
    "ReadFileTool",
    "ReplaceInFileTool",
    "ReturnInspectionTool",
    "RunCommandTool",
    "SearchFilesTool",
    "WebFetchTool",
    "WebSearchTool",
    "WriteFileTool",
]
