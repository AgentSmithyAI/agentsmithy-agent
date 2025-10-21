"""Ephemeral tool for setting dialog title."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from agentsmithy_server.tools.core import result as result_factory
from agentsmithy_server.utils.logger import agent_logger

from ..base_tool import BaseTool

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


class SetDialogTitleArgs(BaseModel):
    """Arguments for set_dialog_title tool."""

    title: str = Field(description="The new title for the current dialog/conversation")


class SetDialogTitleTool(BaseTool):
    """Set the title for the current dialog.

    This tool allows the model to update the title of the current conversation
    based on the content being discussed. The title should be a concise summary
    of the main topic or purpose of the dialog.
    """

    name: str = "set_dialog_title"
    description: str = (
        "Set or update the title of the whole conversation/dialog. "
        "The title MUST be 50 characters or less, brief (ideally 3-8 words) and descriptive."
        "Use it to describe the whole conversation and only update it if the current one doesn't match the conversation."
    )
    args_schema: type[BaseModel] = SetDialogTitleArgs

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._dialog_id: str | None = None
        # This tool should not persist its outputs
        self.ephemeral = True

    def set_context(self, project: Project | None, dialog_id: str | None) -> None:
        """Set project and dialog context for updating title."""
        self._project = project
        self._dialog_id = dialog_id

    async def _arun(self, title: str) -> dict[str, Any]:
        """Set the dialog title.

        Args:
            title: The new title for the dialog

        Returns:
            Dictionary containing success status or error information
        """
        if not self._project or not self._dialog_id:
            return result_factory.error(
                "set_dialog_title",
                "no_context",
                "No dialog context available for setting title",
            )

        if not title or not title.strip():
            return result_factory.error(
                "set_dialog_title",
                "invalid_title",
                "Title cannot be empty",
            )

        # Trim and clean the title
        title = title.strip()

        # Check title length (max 50 characters)
        max_length = 50
        if len(title) > max_length:
            return result_factory.error(
                "set_dialog_title",
                "title_too_long",
                f"Title is too long ({len(title)} characters). Maximum length is {max_length} characters.",
                details={"title_length": len(title), "max_length": max_length},
            )

        try:
            # Update dialog metadata with new title
            self._project.upsert_dialog_meta(self._dialog_id, title=title)

            agent_logger.info(
                "Dialog title updated",
                dialog_id=self._dialog_id,
                title=title,
            )

            return {
                "type": "success",
                "tool": "set_dialog_title",
                "title": title,
                "message": f"Dialog title set to: {title}",
            }

        except Exception as e:
            agent_logger.error(
                "Failed to set dialog title",
                dialog_id=self._dialog_id,
                title=title,
                error=str(e),
            )
            return result_factory.error(
                "set_dialog_title",
                "internal_error",
                f"Failed to set dialog title: {str(e)}",
                error_type=type(e).__name__,
            )
