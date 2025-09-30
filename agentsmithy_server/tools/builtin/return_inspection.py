from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.tools.registry import register_summary_for

from ..base_tool import BaseTool


class ReturnInspectionArgs(BaseModel):
    """Strict schema for project inspection results."""

    language: str = Field(..., description="Main programming language")
    frameworks: list[str] = Field(..., description="Detected frameworks/libraries")
    package_managers: list[str] = Field(..., description="Detected package managers")
    build_tools: list[str] = Field(..., description="Detected build tools")
    architecture_hints: list[str] = Field(
        ..., description="High-level architecture hints (folders, patterns)"
    )


class ReturnInspectionTool(BaseTool):
    name: str = "return_inspection"
    description: str = (
        "Finalize and return the strict JSON analysis of the project. MUST be called once."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = ReturnInspectionArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        # Pydantic validated kwargs match ReturnInspectionArgs
        return {"type": "inspection_result", "analysis": kwargs}


@register_summary_for(ReturnInspectionTool)
def _summarize_return_inspection(args: dict[str, Any], result: dict[str, Any]) -> str:
    if result.get("type") == "inspection_result":
        return "Returned project inspection"
    return "Inspection return"
