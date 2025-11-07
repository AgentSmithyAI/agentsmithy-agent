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


class DeleteFileArgsDict(TypedDict):
    path: str


class DeleteFileSuccess(BaseModel):
    type: Literal["delete_file_result"] = "delete_file_result"
    path: str


DeleteFileResult = DeleteFileSuccess | ToolError


# Summary registration is declared above with imports


class DeleteFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to delete")


class DeleteFileTool(BaseTool):
    name: str = "delete_file"
    description: str = "Delete a file from the workspace (non-recursive)."
    args_schema: type[BaseModel] | dict[str, Any] | None = DeleteFileArgs

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._project = None

    def set_context(self, project, dialog_id):
        """Set project and dialog context for RAG indexing."""
        self._project = project
        self._dialog_id = dialog_id

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

            # Stage file deletion for checkpoint tracking (agent deleted this file)
            try:
                rel_path_obj = file_path.relative_to(project_root)
                tracker.stage_file_deletion(str(rel_path_obj))
            except Exception:
                pass  # Best effort

        # Remove file from RAG (optional, best-effort)
        try:
            if hasattr(self, "_project") and self._project:
                # Get relative path for RAG
                try:
                    rel_path = file_path.relative_to(self._project.root)
                    index_path = str(rel_path)
                except ValueError:
                    # File is outside project root, use absolute path
                    index_path = str(file_path)

                # Remove from vector store
                vector_store = self._project.get_vector_store()
                vector_store.delete_by_source(index_path)
        except Exception:
            # Silently ignore RAG deletion errors
            pass

        if self._sse_callback is not None:
            await self.emit_event(
                {
                    "type": EventType.FILE_EDIT.value,
                    "file": str(file_path),
                }
            )

        return {
            "type": "delete_file_result",
            "path": str(file_path),
        }


@register_summary_for(DeleteFileTool)
def _summarize_delete_file(args: DeleteFileArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, DeleteFileSuccess)
    if isinstance(r, ToolError):
        return f"{args.get('path')}: {r.error}"
    return f"{r.path}"
