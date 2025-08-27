from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


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

        def is_hidden(path: Path) -> bool:
            try:
                relative_parts = path.relative_to(base).parts
            except Exception:
                relative_parts = path.parts
            return any(part.startswith(".") for part in relative_parts)

        try:
            if not base.exists():
                return {
                    "type": "list_files_error",
                    "path": str(base),
                    "error": f"Path does not exist: {base}",
                    "error_type": "PathNotFoundError"
                }
            
            if not base.is_dir():
                return {
                    "type": "list_files_error",
                    "path": str(base),
                    "error": f"Path is not a directory: {base}",
                    "error_type": "NotADirectoryError"
                }

            if recursive:
                for p in base.rglob("*"):
                    if not include_hidden and is_hidden(p):
                        continue
                    items.append(str(p))
            else:
                for p in base.glob("*"):
                    if not include_hidden and is_hidden(p):
                        continue
                    items.append(str(p))
            
            return {"type": "list_files_result", "path": str(base), "items": items}
            
        except PermissionError as e:
            return {
                "type": "list_files_error",
                "path": str(base),
                "error": f"Permission denied accessing directory: {base}",
                "error_type": "PermissionError"
            }
        except Exception as e:
            return {
                "type": "list_files_error",
                "path": str(base),
                "error": f"Error listing directory: {str(e)}",
                "error_type": type(e).__name__
            }
