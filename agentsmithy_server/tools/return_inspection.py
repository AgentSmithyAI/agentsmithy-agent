from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class ReturnInspectionArgs(BaseModel):
    """Strict schema for project inspection results."""

    language: str = Field(..., description="Main programming language")
    frameworks: list[str] = Field(..., description="Detected frameworks/libraries")
    package_managers: list[str] = Field(..., description="Detected package managers")
    build_tools: list[str] = Field(..., description="Detected build tools")
    architecture_hints: list[str] = Field(
        ..., description="High-level architecture hints (folders, patterns)"
    )


class ReturnInspectionTool(BaseTool):  # type: ignore[override]
    name: str = "return_inspection"
    description: str = (
        "Finalize and return the strict JSON analysis of the project. MUST be called once."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = ReturnInspectionArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Pydantic validated kwargs match ReturnInspectionArgs
        return {"type": "inspection_result", "analysis": kwargs}
