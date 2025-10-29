from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy.tools.core import result as result_factory
from agentsmithy.tools.core.types import ToolError, parse_tool_result
from agentsmithy.tools.registry import register_summary_for

from ..base_tool import BaseTool
from ..guards.file_restrictions import get_file_restrictions


class ListFilesArgs(BaseModel):
    path: str = Field(..., description="Directory to list")
    recursive: bool | None = Field(False, description="List recursively if true")
    hidden_files: bool | None = Field(
        False, description="Include hidden (dot-prefixed) files and directories if true"
    )


class ListFilesTool(BaseTool):
    name: str = "list_files"
    description: str = (
        "List files and directories under a path. Hidden (dot-prefixed) files and"
        " directories are excluded by default and must only be included when the"
        " user explicitly requests hidden files (set hidden_files=true)."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = ListFilesArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Use project root if available, fallback to cwd
        import os

        project_root = (
            self._project_root
            if hasattr(self, "_project_root") and self._project_root
            else os.getcwd()
        )

        # Resolve path relative to project root
        input_path = Path(kwargs["path"])
        if input_path.is_absolute():
            base = input_path
        else:
            base = (Path(project_root) / input_path).resolve()

        recursive = bool(kwargs.get("recursive", False))
        include_hidden = bool(kwargs.get("hidden_files", False))
        items: list[str] = []

        # Get file restrictions for workspace
        # Try to find workspace root by looking for .git
        workspace_root = base
        found_marker = False
        while workspace_root.parent != workspace_root:
            if (workspace_root / ".git").exists():
                found_marker = True
                break
            workspace_root = workspace_root.parent

        # If no marker found, use the base directory as workspace root
        if not found_marker:
            workspace_root = base

        restrictions = get_file_restrictions(workspace_root)

        try:
            if not base.exists():
                return result_factory.error(
                    "list_files",
                    code="not_found",
                    message=f"Path does not exist: {base}",
                    error_type="PathNotFoundError",
                    details={"path": str(base)},
                )

            if not base.is_dir():
                return result_factory.error(
                    "list_files",
                    code="not_a_directory",
                    message=f"Path is not a directory: {base}",
                    error_type="NotADirectoryError",
                    details={"path": str(base)},
                )

            # Check if the path is restricted (e.g., root or home directory)
            if restrictions.is_restricted_path(base):
                return result_factory.error(
                    "list_files",
                    code="restricted",
                    message=f"Access to this directory is restricted: {base}",
                    error_type="RestrictedPathError",
                    details={"path": str(base)},
                )

            if recursive:
                for p in base.rglob("*"):
                    # Check if path should be ignored relative to base (not workspace)
                    # This allows listing .github contents when explicitly requested
                    if restrictions.is_ignored_relative_to(p, base):
                        continue
                    # Check if hidden files should be included relative to base
                    # This allows listing .github contents when explicitly requested
                    if not restrictions.should_include_hidden_relative_to(
                        p, base, include_hidden
                    ):
                        continue
                    items.append(str(p))
            else:
                for p in base.glob("*"):
                    # Check if path should be ignored relative to base (not workspace)
                    # This allows listing .github contents when explicitly requested
                    if restrictions.is_ignored_relative_to(p, base):
                        continue
                    # Check if hidden files should be included relative to base
                    # This allows listing .github contents when explicitly requested
                    if not restrictions.should_include_hidden_relative_to(
                        p, base, include_hidden
                    ):
                        continue
                    items.append(str(p))

            return {
                "type": "list_files_result",
                "path": str(base),
                "items": sorted(items),
            }

        except PermissionError:
            return result_factory.error(
                "list_files",
                code="permission_denied",
                message=f"Permission denied accessing directory: {base}",
                error_type="PermissionError",
                details={"path": str(base)},
            )
        except Exception as e:
            return result_factory.error(
                "list_files",
                code="exception",
                message=f"Error listing directory: {str(e)}",
                error_type=type(e).__name__,
                details={"path": str(base)},
            )


# Summary registration for tools
# Local TypedDicts for type hints


class ListFilesArgsDict(TypedDict, total=False):
    path: str
    recursive: bool
    hidden_files: bool


class ListFilesSuccess(BaseModel):
    type: Literal["list_files_result"] = "list_files_result"
    path: str
    items: list[str]


ListFilesResult = ListFilesSuccess | ToolError


@register_summary_for(ListFilesTool)
def _summarize_list_files(args: ListFilesArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, ListFilesSuccess)
    if isinstance(r, ToolError):
        return f"{args.get('path')}: {r.error}"
    return f"{r.path}: {len(r.items)} items"
