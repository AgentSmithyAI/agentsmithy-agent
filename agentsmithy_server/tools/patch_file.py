from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from pydantic import BaseModel, Field

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
    changes: List[dict] = Field(..., description="List of change objects")


class PatchFileTool(BaseTool):
    name = "patch_file"
    description = "Apply multiple line-range changes to a file and emit diff events."
    args_schema = PatchArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["file_path"]).resolve()
        changes: List[dict[str, Any]] = kwargs.get("changes", [])

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
        new_text = "\n".join(modified_lines) + ("\n" if original_text.endswith("\n") else "")
        file_path.write_text(new_text, encoding="utf-8")

        # Compute diff for entire file
        unified = "\n".join(
            difflib.unified_diff(
                original_text.splitlines(),
                new_text.splitlines(),
                fromfile=str(file_path),
                tofile=str(file_path),
                lineterm="",
            )
        )

        # Emit diff event compatible with SSE protocol
        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": "diff",
                    "file": str(file_path),
                    "diff": unified,
                    "reason": "; ".join([c.reason for c in parsed_changes if c.reason]),
                }
            )

        return {
            "type": "patch_result",
            "file": str(file_path),
            "diff": unified,
            "applied_changes": [c.__dict__ for c in parsed_changes],
        }


