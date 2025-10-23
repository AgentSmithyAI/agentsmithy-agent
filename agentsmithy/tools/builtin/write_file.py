from __future__ import annotations

import os
from pathlib import Path

# Local TypedDicts for type hints
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy.domain.events import EventType
from agentsmithy.services.versioning import VersioningTracker
from agentsmithy.tools.core.types import ToolError, parse_tool_result
from agentsmithy.tools.registry import register_summary_for

from ..base_tool import BaseTool


class WriteFileArgsDict(TypedDict):
    path: str
    content: str


class WriteFileSuccess(BaseModel):
    type: Literal["write_file_result"] = "write_file_result"
    path: str
    checkpoint: str | None = None


WriteFileResult = WriteFileSuccess | ToolError


# Summary registration is declared above with imports


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to write")
    content: str = Field(..., description="Complete file content to write")


class WriteFileTool(BaseTool):
    name: str = "write_to_file"
    description: str = "Write complete content to a file (create or overwrite)."
    args_schema: type[BaseModel] | dict[str, Any] | None = WriteFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Use project root if available, fallback to cwd
        project_root = (
            self._project_root
            if hasattr(self, "_project_root") and self._project_root
            else os.getcwd()
        )

        # Resolve path relative to project root
        input_path = Path(kwargs["path"])
        if input_path.is_absolute():
            file_path = input_path
        else:
            file_path = (Path(project_root) / input_path).resolve()

        tracker = VersioningTracker(project_root, dialog_id=self._dialog_id)
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = None
        try:
            file_path.write_text(kwargs["content"], encoding="utf-8")
        except Exception:
            # revert attempt
            tracker.abort_edit()
            raise
        else:
            tracker.finalize_edit()
            # Track change in transaction or create immediate checkpoint
            rel_path = (
                str(file_path.relative_to(project_root))
                if file_path.is_relative_to(project_root)
                else str(file_path)
            )
            if tracker.is_transaction_active():
                tracker.track_file_change(rel_path, "write")
            else:
                checkpoint = tracker.create_checkpoint(f"write_to_file: {rel_path}")
        # Emit file_edit event in simplified SSE protocol
        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": EventType.FILE_EDIT.value,
                    "file": str(file_path),
                }
            )
        return {
            "type": "write_file_result",
            "path": str(file_path),
            "checkpoint": getattr(checkpoint, "commit_id", None),
        }


@register_summary_for(WriteFileTool)
def _summarize_write_file(args: WriteFileArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, WriteFileSuccess)
    if isinstance(r, ToolError):
        return f"{args.get('path')}: {r.error}"
    content_len = len(args.get("content", ""))
    return f"{r.path}: {content_len} bytes"
