from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agentsmithy_server.tools.core.types import ToolError, parse_tool_result
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


class ReturnInspectionSuccess(BaseModel):
    type: Literal["inspection_result"] = "inspection_result"
    analysis: dict[str, Any]


ReturnInspectionResult = ReturnInspectionSuccess | ToolError


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
    r = parse_tool_result(result, ReturnInspectionSuccess)
    if isinstance(r, ToolError):
        return f"Inspection failed: {r.error}"
    lang = args.get("language", "unknown")
    frameworks = args.get("frameworks", [])
    return f"Project inspection: {lang}, {len(frameworks)} frameworks"
