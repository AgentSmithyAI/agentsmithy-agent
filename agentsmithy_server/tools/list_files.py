from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class ListFilesArgs(BaseModel):
    path: str = Field(..., description="Directory to list")
    recursive: bool | None = Field(False, description="List recursively if true")


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories under a path."
    args_schema = ListFilesArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        base = Path(kwargs["path"]).resolve()
        recursive = bool(kwargs.get("recursive", False))
        items: list[str] = []
        if recursive:
            for p in base.rglob("*"):
                items.append(str(p))
        else:
            for p in base.glob("*"):
                items.append(str(p))
        return {"type": "list_files_result", "path": str(base), "items": items}
