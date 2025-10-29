from __future__ import annotations

import os
import re
from pathlib import Path

# Local TypedDicts for type hints
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy.tools.core import result as result_factory
from agentsmithy.tools.core.types import ToolError, parse_tool_result
from agentsmithy.tools.registry import register_summary_for
from agentsmithy.utils.logger import agent_logger

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

        # Limits to prevent resource exhaustion
        MAX_FILES_TO_SCAN = 2000
        MAX_FILE_SIZE_BYTES = 10_000_000  # 10MB
        MAX_RESULTS = 1000

        files_scanned = 0
        results_found = 0

        def _should_match_glob(file_path: Path) -> bool:
            """Check if file matches the glob pattern."""
            if file_glob == "**/*":
                return True
            # Use pathlib's match for proper glob matching
            try:
                return file_path.match(file_glob)
            except (ValueError, re.error):
                # Fallback to True if pattern is invalid
                return True

        def _search_in_file(file_path: Path) -> list[dict[str, Any]]:
            """Search for pattern in a single file using efficient line-by-line reading."""
            nonlocal results_found
            file_results: list[dict[str, Any]] = []

            # Check file size first
            try:
                file_size = file_path.stat().st_size
                if file_size > MAX_FILE_SIZE_BYTES:
                    agent_logger.debug(
                        "Skipping large file",
                        file=str(file_path),
                        size=file_size,
                    )
                    return file_results
            except Exception:
                return file_results

            # Read file into lines for easier context extraction
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    lines = [line.rstrip("\n\r") for line in f]
            except Exception as e:
                agent_logger.debug(
                    "Error reading file", file=str(file_path), error=str(e)
                )
                return file_results

            # Search through lines and build context
            for i, line in enumerate(lines):
                if results_found >= MAX_RESULTS:
                    break

                if regex.search(line):
                    line_num = i + 1
                    # Calculate context window (2 lines before, current, 2 lines after)
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = "\n".join(lines[start:end])

                    file_results.append(
                        {
                            "file": str(file_path),
                            "line": line_num,
                            "context": context,
                        }
                    )
                    results_found += 1

            return file_results

        def _walk_directory(directory: Path) -> None:
            """Recursively walk directory using os.scandir (faster than glob)."""
            nonlocal files_scanned, results_found

            if files_scanned >= MAX_FILES_TO_SCAN or results_found >= MAX_RESULTS:
                return

            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if (
                            files_scanned >= MAX_FILES_TO_SCAN
                            or results_found >= MAX_RESULTS
                        ):
                            break

                        try:
                            entry_path = Path(entry.path)

                            # Check restrictions
                            if restrictions.is_ignored_relative_to(entry_path, base):
                                continue

                            if entry.is_dir(follow_symlinks=False):
                                # Skip hidden directories unless explicitly requested
                                if not restrictions.should_include_hidden_relative_to(
                                    entry_path,
                                    base,
                                    ".*" in file_glob or "/." in file_glob,
                                ):
                                    continue
                                _walk_directory(entry_path)

                            elif entry.is_file(follow_symlinks=False):
                                # Skip hidden files unless explicitly requested
                                if not restrictions.should_include_hidden_relative_to(
                                    entry_path,
                                    base,
                                    ".*" in file_glob or "/." in file_glob,
                                ):
                                    continue

                                # Check glob pattern
                                if not _should_match_glob(entry_path):
                                    continue

                                files_scanned += 1
                                file_results = _search_in_file(entry_path)
                                results.extend(file_results)

                        except (PermissionError, OSError):
                            continue

            except (PermissionError, OSError):
                pass

        try:
            _walk_directory(base)

            # Log if limits were hit
            if files_scanned >= MAX_FILES_TO_SCAN:
                agent_logger.info(
                    "Search stopped: max files scanned limit reached",
                    files_scanned=files_scanned,
                    limit=MAX_FILES_TO_SCAN,
                )
            if results_found >= MAX_RESULTS:
                agent_logger.info(
                    "Search stopped: max results limit reached",
                    results_found=results_found,
                    limit=MAX_RESULTS,
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
