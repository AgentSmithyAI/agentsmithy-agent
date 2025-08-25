from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to write")
    content: str = Field(..., description="Complete file content to write")


class WriteFileTool(BaseTool):
    name: str = "write_to_file"
    description: str = "Write complete content to a file (create or overwrite)."
    args_schema: type[BaseModel] = WriteFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(kwargs["content"], encoding="utf-8")
        # Emit file_edit event in simplified SSE protocol
        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": "file_edit",
                    "file": str(file_path),
                }
            )
        return {"type": "write_file_result", "path": str(file_path)}
