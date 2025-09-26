from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..base_tool import BaseTool
from ..guards.file_restrictions import get_file_restrictions


class ListFilesArgs(BaseModel):
    path: str = Field(..., description="Directory to list")
    recursive: bool | None = Field(False, description="List recursively if true")
    hidden_files: bool | None = Field(
        False, description="Include hidden (dot-prefixed) files and directories if true"
    )


class ListFilesTool(BaseTool):  # type: ignore[override]
    name: str = "list_files"
    description: str = (
        "List files and directories under a path. Hidden (dot-prefixed) files and"
        " directories are excluded by default and must only be included when the"
        " user explicitly requests hidden files (set hidden_files=true)."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = ListFilesArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        base = Path(kwargs["path"]).resolve()
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
                return {
                    "type": "list_files_error",
                    "path": str(base),
                    "error": f"Path does not exist: {base}",
                    "error_type": "PathNotFoundError",
                }

            if not base.is_dir():
                return {
                    "type": "list_files_error",
                    "path": str(base),
                    "error": f"Path is not a directory: {base}",
                    "error_type": "NotADirectoryError",
                }

            # Check if the path is restricted (e.g., root or home directory)
            if restrictions.is_restricted_path(base):
                return {
                    "type": "list_files_error",
                    "path": str(base),
                    "error": f"Access to this directory is restricted: {base}",
                    "error_type": "RestrictedPathError",
                }

            if recursive:
                for p in base.rglob("*"):
                    # Check if path should be ignored by restrictions
                    if restrictions.is_ignored(p):
                        continue
                    # Check if hidden files should be included
                    if not restrictions.should_include_hidden(p, include_hidden):
                        continue
                    items.append(str(p))
            else:
                for p in base.glob("*"):
                    # Check if path should be ignored by restrictions
                    if restrictions.is_ignored(p):
                        continue
                    # Check if hidden files should be included
                    if not restrictions.should_include_hidden(p, include_hidden):
                        continue
                    items.append(str(p))

            return {
                "type": "list_files_result",
                "path": str(base),
                "items": sorted(items),
            }

        except PermissionError:
            return {
                "type": "list_files_error",
                "path": str(base),
                "error": f"Permission denied accessing directory: {base}",
                "error_type": "PermissionError",
            }
        except Exception as e:
            return {
                "type": "list_files_error",
                "path": str(base),
                "error": f"Error listing directory: {str(e)}",
                "error_type": type(e).__name__,
            }
