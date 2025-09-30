"""Tool for retrieving results from previous tool executions."""

from __future__ import annotations

# Local TypedDicts for type hints
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agentsmithy_server.core.tool_results_storage import ToolResultsStorage
from agentsmithy_server.tools.core import result as result_factory
from agentsmithy_server.tools.registry import register_summary_for
from agentsmithy_server.utils.logger import agent_logger

from ..base_tool import BaseTool


class GetPreviousResultArgsDict(TypedDict):
    tool_call_id: str


class PreviousResultSuccess(TypedDict, total=False):
    type: Literal["previous_result"]
    tool_call_id: str
    tool_name: str | None
    original_args: dict[str, Any] | None
    result: dict[str, Any] | None
    timestamp: float | int | None


# Summary registration is declared above with imports

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


class GetPreviousResultArgs(BaseModel):
    """Arguments for get_tool_result tool."""

    tool_call_id: str = Field(
        description="The ID of a PREVIOUS tool call from EARLIER in the conversation whose results you need to retrieve"
    )


class GetPreviousResultTool(BaseTool):
    """Retrieve results from previous tool executions in this dialog.

    This tool allows the model to access full results from PREVIOUS tool
    executions that were performed EARLIER in the conversation. It should
    NOT be used to retrieve results of tools that were just executed in
    the current task context.
    """

    name: str = "get_tool_result"
    description: str = (
        "Retrieve the full result of a PREVIOUS tool execution from EARLIER in the conversation. "
        "ONLY use this when you need specific data from a tool that was executed BEFORE the current task, "
        "and that data is REQUIRED to complete your current objective. Do not use this for retrieving results "
        "of file operations, it's more correct to use the appropriate file operation tool again. "
        "This is especially important for non-idempotent tools, like web search, where running the tool again may yield different results. "
        "Retrieving the previous result ensures consistency and avoids unnecessary repeated actions."
    )
    args_schema: type[BaseModel] = GetPreviousResultArgs

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._dialog_id: str | None = None
        # This tool should not persist its own outputs
        self.ephemeral = True

    def set_context(self, project: Project | None, dialog_id: str | None) -> None:
        """Set project and dialog context for accessing tool results."""
        self._project = project
        self._dialog_id = dialog_id

    async def _arun(self, tool_call_id: str) -> dict[str, Any]:
        """Retrieve previous tool result by ID.

        Args:
            tool_call_id: The ID of the tool call to retrieve

        Returns:
            Dictionary containing the tool result or error information
        """
        if not self._project or not self._dialog_id:
            return result_factory.error(
                "get_tool_result",
                "no_context",
                "No dialog context available for retrieving tool results",
            )

        try:
            storage = ToolResultsStorage(self._project, self._dialog_id)
            result_data = await storage.get_result(tool_call_id)

            if not result_data:
                # List available tool results to help the user
                available = await storage.list_results()
                available_ids = [r.tool_call_id for r in available[:10]]  # Show max 10

                return result_factory.not_found(
                    "get_tool_result",
                    "tool_result",
                    tool_call_id,
                    hint=(
                        "Use one of the available tool_call_ids listed above. Remember: this tool is for retrieving results from EARLIER in the conversation, not for tools you just executed."
                    ),
                    extra={"available_tool_call_ids": available_ids},
                )

            agent_logger.info(
                "Retrieved previous tool result",
                tool_call_id=tool_call_id,
                tool_name=result_data.get("tool_name"),
            )

            # Return the full result data
            return {
                "type": "previous_result",
                "tool_call_id": tool_call_id,
                "tool_name": result_data.get("tool_name"),
                "original_args": result_data.get("args"),
                "result": result_data.get("result"),
                "timestamp": result_data.get("timestamp"),
            }

        except Exception as e:
            agent_logger.error(
                "Failed to retrieve tool result",
                tool_call_id=tool_call_id,
                error=str(e),
            )
            return result_factory.error(
                "get_tool_result",
                "internal_error",
                f"Failed to retrieve tool result: {str(e)}",
                error_type=type(e).__name__,
            )


@register_summary_for(GetPreviousResultTool)
def _summarize_get_previous_result(
    args: GetPreviousResultArgsDict, result: PreviousResultSuccess | dict[str, Any]
) -> str:
    if result.get("type") != "previous_result":
        return "Previous tool result not found"
    name = result.get("tool_name") or "tool"
    return f"Loaded previous result for {name}"
