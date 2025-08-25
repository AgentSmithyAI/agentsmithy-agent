from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool
from agentsmithy_server.services.versioning import VersioningTracker


class ReplaceArgs(BaseModel):
    path: str = Field(..., description="Path to file to modify")
    diff: str = Field(
        ...,
        description="One or more SEARCH/REPLACE blocks as specified by Cline format",
    )


class ReplaceInFileTool(BaseTool):  # type: ignore[override]
    name: str = "replace_in_file"
    description: str = "Apply targeted edits to a file using SEARCH/REPLACE blocks."
    args_schema: type[BaseModel] | dict[str, Any] | None = ReplaceArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Minimal placeholder: begin an edit session so we can revert on error, but
        # we don't apply the diff here yet (parser/constructor can be added later).
        file_path = Path(kwargs["path"]).resolve()
        tracker = VersioningTracker(os.getcwd())
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])
        # No changes are made here; finalize immediately and create a checkpoint of current state
        tracker.finalize_edit()
        tracker.create_checkpoint(f"replace_in_file request: {str(file_path)}")
        return {
            "type": "replace_file_request",
            "path": str(file_path),
            "diff": kwargs["diff"],
        }
