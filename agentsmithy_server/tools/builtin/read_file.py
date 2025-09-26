from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..base_tool import BaseTool


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to read")


class ReadFileTool(BaseTool):  # type: ignore[override]
    name: str = "read_file"
    description: str = "Read the contents of a file at the specified path."
    args_schema: type[BaseModel] | dict[str, Any] | None = ReadFileArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()

        try:
            if not file_path.exists():
                return {
                    "type": "read_file_error",
                    "path": str(file_path),
                    "error": f"File not found: {file_path}",
                    "error_type": "FileNotFoundError",
                }

            if not file_path.is_file():
                return {
                    "type": "read_file_error",
                    "path": str(file_path),
                    "error": f"Path is not a file: {file_path}",
                    "error_type": "NotAFileError",
                }

            content = file_path.read_text(encoding="utf-8")
            return {
                "type": "read_file_result",
                "path": str(file_path),
                "content": content,
            }

        except PermissionError:
            return {
                "type": "read_file_error",
                "path": str(file_path),
                "error": f"Permission denied reading file: {file_path}",
                "error_type": "PermissionError",
            }
        except UnicodeDecodeError:
            return {
                "type": "read_file_error",
                "path": str(file_path),
                "error": f"File is not a valid UTF-8 text file: {file_path}",
                "error_type": "UnicodeDecodeError",
            }
        except Exception as e:
            return {
                "type": "read_file_error",
                "path": str(file_path),
                "error": f"Error reading file: {str(e)}",
                "error_type": type(e).__name__,
            }
