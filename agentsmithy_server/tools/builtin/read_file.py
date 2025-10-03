from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy_server.tools.core import result as result_factory
from agentsmithy_server.tools.core.types import ToolError, parse_tool_result
from agentsmithy_server.tools.registry import register_summary_for

from ..base_tool import BaseTool


class ReadFileArgsDict(TypedDict):
    path: str


class ReadFileSuccess(BaseModel):
    type: Literal["read_file_result"] = "read_file_result"
    path: str
    content: str


ReadFileResult = ReadFileSuccess | ToolError

# Summary registration is declared above with imports


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to read")


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "Read the contents of a file at the specified path."
    args_schema: type[BaseModel] | dict[str, Any] | None = ReadFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Use project root if available, fallback to cwd
        import os

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

        try:
            if not file_path.exists():
                return result_factory.error(
                    "read_file",
                    code="not_found",
                    message=f"File not found: {file_path}",
                    error_type="FileNotFoundError",
                    details={"path": str(file_path)},
                )

            if not file_path.is_file():
                return result_factory.error(
                    "read_file",
                    code="not_a_file",
                    message=f"Path is not a file: {file_path}",
                    error_type="NotAFileError",
                    details={"path": str(file_path)},
                )

            content = file_path.read_text(encoding="utf-8")
            return ReadFileSuccess(
                path=str(file_path),
                content=content,
            ).model_dump()

        except PermissionError:
            return result_factory.error(
                "read_file",
                code="permission_denied",
                message=f"Permission denied reading file: {file_path}",
                error_type="PermissionError",
                details={"path": str(file_path)},
            )
        except UnicodeDecodeError:
            return result_factory.error(
                "read_file",
                code="decode_error",
                message=f"File is not a valid UTF-8 text file: {file_path}",
                error_type="UnicodeDecodeError",
                details={"path": str(file_path)},
            )
        except Exception as e:
            return result_factory.error(
                "read_file",
                code="exception",
                message=f"Error reading file: {str(e)}",
                error_type=type(e).__name__,
                details={"path": str(file_path)},
            )


@register_summary_for(ReadFileTool)
def _summarize_read_file(args: ReadFileArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, ReadFileSuccess)
    if isinstance(r, ToolError):
        return f"{args.get('path')}: {r.error}"

    preview = r.content.splitlines()[0].strip() if r.content else ""
    if preview:
        return f"{r.path} ({len(r.content)} bytes) - {preview[:60]}"
    return f"{r.path} ({len(r.content)} bytes)"
