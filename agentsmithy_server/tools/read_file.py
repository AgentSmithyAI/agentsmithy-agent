from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to read")


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "Read the contents of a file at the specified path."
    args_schema: type[BaseModel] = ReadFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()
        content = file_path.read_text(encoding="utf-8")
        return {"type": "read_file_result", "path": str(file_path), "content": content}
