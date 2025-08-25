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
    description: str = "List files and directories under a path."
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
