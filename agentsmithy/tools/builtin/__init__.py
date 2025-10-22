"""Builtin tool package.

Static export of tool classes for reliable bundling and registration.

Why static: Dynamic discovery via pkgutil/importlib doesn't work in
PyInstaller onefile binaries because packages are not visible as FS dirs.
Keeping an explicit list ensures tools are included and registered.
"""

from __future__ import annotations

from agentsmithy.tools.builtin.delete_file import DeleteFileTool
from agentsmithy.tools.builtin.get_previous_result import (
    GetPreviousResultTool,
)
from agentsmithy.tools.builtin.list_files import ListFilesTool
from agentsmithy.tools.builtin.read_file import ReadFileTool
from agentsmithy.tools.builtin.replace_in_file import ReplaceInFileTool
from agentsmithy.tools.builtin.return_inspection import (
    ReturnInspectionTool,
)
from agentsmithy.tools.builtin.run_command import RunCommandTool
from agentsmithy.tools.builtin.search_files import SearchFilesTool
from agentsmithy.tools.builtin.set_dialog_title import SetDialogTitleTool
from agentsmithy.tools.builtin.web_fetch import WebFetchTool
from agentsmithy.tools.builtin.web_search import WebSearchTool
from agentsmithy.tools.builtin.write_file import WriteFileTool

TOOL_CLASSES = [
    DeleteFileTool,
    GetPreviousResultTool,
    ListFilesTool,
    ReadFileTool,
    ReplaceInFileTool,
    ReturnInspectionTool,
    RunCommandTool,
    SearchFilesTool,
    SetDialogTitleTool,
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
    "SetDialogTitleTool",
    "WebFetchTool",
    "WebSearchTool",
    "WriteFileTool",
]
