from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..base_tool import BaseTool
from ..guards.file_restrictions import get_file_restrictions


class SearchFilesArgs(BaseModel):
    path: str = Field(..., description="Directory to search")
    regex: str = Field(..., description="Regex pattern (Python syntax)")
    file_pattern: str | None = Field(None, description="Glob to filter files")


class SearchFilesTool(BaseTool):
    name: str = "search_files"
    description: str = (
        "Regex search across files in a directory, returning context lines."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = SearchFilesArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        base = Path(kwargs["path"]).resolve()
        pattern = kwargs["regex"]
        file_glob = kwargs.get("file_pattern") or "**/*"

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
                    "type": "search_files_error",
                    "path": str(base),
                    "error": f"Path does not exist: {base}",
                    "error_type": "PathNotFoundError",
                }

            if not base.is_dir():
                return {
                    "type": "search_files_error",
                    "path": str(base),
                    "error": f"Path is not a directory: {base}",
                    "error_type": "NotADirectoryError",
                }

            # Check if the path is restricted (e.g., root or home directory)
            if restrictions.is_restricted_path(base):
                return {
                    "type": "search_files_error",
                    "path": str(base),
                    "error": f"Access to this directory is restricted: {base}",
                    "error_type": "RestrictedPathError",
                }

            regex = re.compile(pattern)
        except re.error as e:
            return {
                "type": "search_files_error",
                "path": str(base),
                "error": f"Invalid regex pattern: {pattern} - {str(e)}",
                "error_type": "RegexError",
            }

        results: list[dict[str, Any]] = []

        try:
            for file_path in base.glob(file_glob):
                if not file_path.is_file():
                    continue

                # Check if file should be ignored by restrictions
                if restrictions.is_ignored(file_path):
                    continue

                # Skip hidden files unless they match the glob pattern explicitly
                if not restrictions.should_include_hidden(
                    file_path, ".*" in file_glob or "/." in file_glob
                ):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                lines = content.splitlines()
                for i, line in enumerate(lines, start=1):
                    if regex.search(line):
                        start = max(1, i - 2)
                        end = min(len(lines), i + 2)
                        context = "\n".join(lines[start - 1 : end])
                        results.append(
                            {"file": str(file_path), "line": i, "context": context}
                        )

            return {"type": "search_files_result", "results": results}

        except PermissionError:
            return {
                "type": "search_files_error",
                "path": str(base),
                "error": f"Permission denied accessing directory: {base}",
                "error_type": "PermissionError",
            }
        except Exception as e:
            return {
                "type": "search_files_error",
                "path": str(base),
                "error": f"Error searching files: {str(e)}",
                "error_type": type(e).__name__,
            }
