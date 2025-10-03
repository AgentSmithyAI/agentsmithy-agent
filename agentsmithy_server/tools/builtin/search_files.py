from __future__ import annotations

import re
from pathlib import Path

# Local TypedDicts for type hints
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy_server.tools.core import result as result_factory
from agentsmithy_server.tools.core.types import ToolError, parse_tool_result
from agentsmithy_server.tools.registry import register_summary_for

from ..base_tool import BaseTool
from ..guards.file_restrictions import get_file_restrictions


class SearchFilesArgsDict(TypedDict, total=False):
    path: str
    regex: str
    file_pattern: str | None


class SearchFilesSuccess(BaseModel):
    type: Literal["search_files_result"] = "search_files_result"
    results: list[dict[str, Any]]


SearchFilesResult = SearchFilesSuccess | ToolError

# Summary registration is declared above with imports


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
                return result_factory.error(
                    "search_files",
                    code="not_found",
                    message=f"Path does not exist: {base}",
                    error_type="PathNotFoundError",
                    details={"path": str(base)},
                )

            if not base.is_dir():
                return result_factory.error(
                    "search_files",
                    code="not_a_directory",
                    message=f"Path is not a directory: {base}",
                    error_type="NotADirectoryError",
                    details={"path": str(base)},
                )

            # Check if the path is restricted (e.g., root or home directory)
            if restrictions.is_restricted_path(base):
                return result_factory.error(
                    "search_files",
                    code="restricted",
                    message=f"Access to this directory is restricted: {base}",
                    error_type="RestrictedPathError",
                    details={"path": str(base)},
                )

            regex = re.compile(pattern)
        except re.error as e:
            return result_factory.error(
                "search_files",
                code="regex_error",
                message=f"Invalid regex pattern: {pattern} - {str(e)}",
                error_type="RegexError",
                details={"path": str(base), "regex": pattern},
            )

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
            return result_factory.error(
                "search_files",
                code="permission_denied",
                message=f"Permission denied accessing directory: {base}",
                error_type="PermissionError",
                details={"path": str(base)},
            )
        except Exception as e:
            return result_factory.error(
                "search_files",
                code="exception",
                message=f"Error searching files: {str(e)}",
                error_type=type(e).__name__,
                details={
                    "path": str(base),
                    "regex": pattern,
                    "file_pattern": file_glob,
                },
            )


@register_summary_for(SearchFilesTool)
def _summarize_search_files(args: SearchFilesArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, SearchFilesSuccess)
    if isinstance(r, ToolError):
        return f"{args.get('path')}: {r.error}"
    regex = args.get("regex", "")
    return f"{args.get('path')} '{regex}': {len(r.results)} matches"
