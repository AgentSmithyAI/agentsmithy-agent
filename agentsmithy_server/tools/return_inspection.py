from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


class ReturnInspectionArgs(BaseModel):
    """Strict schema for project inspection results."""

    language_stats: dict[str, int] = Field(
        ..., description="Mapping from language name to file/count estimate"
    )
    dominant_languages: list[str] = Field(..., description="Top languages by presence")
    frameworks: list[str] = Field(..., description="Detected frameworks/libraries")
    package_managers: list[str] = Field(..., description="Detected package managers")
    build_tools: list[str] = Field(..., description="Detected build tools")
    has_tests: bool = Field(..., description="Whether tests are present")
    test_frameworks: list[str] = Field(..., description="Detected test frameworks")
    architecture_hints: list[str] = Field(
        ..., description="High-level architecture hints (folders, patterns)"
    )


class ReturnInspectionTool(BaseTool):
    name: str = "return_inspection"
    description: str = (
        "Finalize and return the strict JSON analysis of the project. MUST be called once."
    )
    args_schema: type[BaseModel] = ReturnInspectionArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Pydantic validated kwargs match ReturnInspectionArgs
        return {"type": "inspection_result", "analysis": kwargs}
