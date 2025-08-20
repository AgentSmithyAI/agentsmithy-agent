from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class SearchFilesArgs(BaseModel):
    path: str = Field(..., description="Directory to search")
    regex: str = Field(..., description="Regex pattern (Python syntax)")
    file_pattern: str | None = Field(None, description="Glob to filter files")


class SearchFilesTool(BaseTool):
    name: str = "search_files"
    description: str = (
        "Regex search across files in a directory, returning context lines."
    )
    args_schema: type[BaseModel] = SearchFilesArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        base = Path(kwargs["path"]).resolve()
        pattern = kwargs["regex"]
        file_glob = kwargs.get("file_pattern") or "**/*"

        regex = re.compile(pattern)
        results: list[dict[str, Any]] = []

        for file_path in base.glob(file_glob):
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = content.splitlines()
            for i, line in enumerate(lines, start=1):
                if regex.search(line):
                    start = max(1, i - 2)
                    end = min(len(lines), i + 2)
                    context = "\n".join(lines[start - 1 : end])
                    results.append(
                        {"file": str(file_path), "line": i, "context": context}
                    )

        return {"type": "search_files_result", "results": results}
