from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.services.versioning import VersioningTracker

from .base_tool import BaseTool


class DeleteFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to delete")


class DeleteFileTool(BaseTool):  # type: ignore[override]
    name: str = "delete_file"
    description: str = "Delete a file from the workspace (non-recursive)."
    args_schema: type[BaseModel] | dict[str, Any] | None = DeleteFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()

        tracker = VersioningTracker(os.getcwd(), dialog_id=self._dialog_id)
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])

        checkpoint = None
        try:
            if file_path.exists():
                if file_path.is_file():
                    file_path.unlink()
                else:
                    raise ValueError(
                        "Path is not a file. Use a directory removal tool if intended."
                    )
            # else: no-op if already absent
        except Exception:
            tracker.abort_edit()
            raise
        else:
            tracker.finalize_edit()
            checkpoint = tracker.create_checkpoint(f"delete_file: {str(file_path)}")

        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": "file_edit",
                    "file": str(file_path),
                    "checkpoint": getattr(checkpoint, "commit_id", None),
                }
            )

        return {
            "type": "delete_file_result",
            "path": str(file_path),
            "checkpoint": getattr(checkpoint, "commit_id", None),
        }
