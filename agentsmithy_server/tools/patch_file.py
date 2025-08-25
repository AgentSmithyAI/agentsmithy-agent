from __future__ import annotations

import os
from dataclasses import dataclass
import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.services.versioning import VersioningTracker

from .base_tool import BaseTool


@dataclass
class FileChange:
    line_start: int
    line_end: int
    old_content: str
    new_content: str
    reason: str


class PatchArgs(BaseModel):
    file_path: str = Field(..., description="Path to file to modify")
    changes: list[dict] = Field(..., description="List of change objects")


class PatchFileTool(BaseTool):  # type: ignore[override]
    name: str = "patch_file"
    description: str = (
        "Apply multiple line-range changes to a file and emit diff events."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = PatchArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["file_path"]).resolve()
        changes: list[dict[str, Any]] = kwargs.get("changes", [])

        tracker = VersioningTracker(os.getcwd())
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])

        # Read original file content
        original_text = file_path.read_text(encoding="utf-8")
        original_lines = original_text.splitlines()

        # Sort changes by start line descending to avoid index shifts
        parsed_changes = [
            FileChange(
                line_start=c["line_start"],
                line_end=c["line_end"],
                old_content=c.get("old_content", ""),
                new_content=c.get("new_content", ""),
                reason=c.get("reason", ""),
            )
            for c in changes
        ]
        parsed_changes.sort(key=lambda c: c.line_start, reverse=True)

        # Apply changes bottom-up
        modified_lines = original_lines[:]
        for change in parsed_changes:
            start_idx = max(0, change.line_start - 1)
            end_idx = max(0, change.line_end)

            # Replace the slice with new content lines
            new_lines = change.new_content.splitlines()
            modified_lines[start_idx:end_idx] = new_lines

        # Write updated content
        new_text = "\n".join(modified_lines) + (
            "\n" if original_text.endswith("\n") else ""
        )
        try:
            file_path.write_text(new_text, encoding="utf-8")
        except Exception:
            tracker.abort_edit()
            raise
        else:
            tracker.finalize_edit()
            checkpoint = tracker.create_checkpoint(f"patch_file: {str(file_path)}")

        # Emit file_edit event with diff and checkpoint
        if self._sse_callback is not None:
            unified = difflib.unified_diff(
                original_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
            diff_str = "\n".join(unified)
            await self.emit_event(
                {
                    "type": "file_edit",
                    "file": str(file_path),
                    "diff": diff_str,
                    "checkpoint": getattr(checkpoint, "commit_id", None),
                }
            )

        return {
            "type": "patch_result",
            "file": str(file_path),
            "applied_changes": [c.__dict__ for c in parsed_changes],
        }
