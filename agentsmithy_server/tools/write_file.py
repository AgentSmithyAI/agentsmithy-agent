from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.services.versioning import VersioningTracker

from .base_tool import BaseTool


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to write")
    content: str = Field(..., description="Complete file content to write")


class WriteFileTool(BaseTool):  # type: ignore[override]
    name: str = "write_to_file"
    description: str = "Write complete content to a file (create or overwrite)."
    args_schema: type[BaseModel] | dict[str, Any] | None = WriteFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()
        tracker = VersioningTracker(os.getcwd(), dialog_id=self._dialog_id)
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_path.write_text(kwargs["content"], encoding="utf-8")
        except Exception:
            # revert attempt
            tracker.abort_edit()
            raise
        else:
            tracker.finalize_edit()
            checkpoint = tracker.create_checkpoint(f"write_to_file: {str(file_path)}")
        # Emit file_edit event in simplified SSE protocol
        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": "file_edit",
                    "file": str(file_path),
                    "checkpoint": getattr(checkpoint, "commit_id", None),
                }
            )
        return {
            "type": "write_file_result",
            "path": str(file_path),
            "checkpoint": getattr(checkpoint, "commit_id", None),
        }
