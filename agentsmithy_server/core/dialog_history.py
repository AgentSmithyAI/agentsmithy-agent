"""File-based dialog history management using LangChain."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.messages import BaseMessage

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


class DialogHistory:
    """Manages dialog history using file storage through LangChain's FileChatMessageHistory."""

    def __init__(self, project: Project, dialog_id: str):
        self.project = project
        self.dialog_id = dialog_id
        self._history: FileChatMessageHistory | None = None

    @property
    def history_file_path(self) -> Path:
        """Get the history file path for this dialog."""
        dialog_dir = self.project.get_dialog_dir(self.dialog_id)
        dialog_dir.mkdir(parents=True, exist_ok=True)
        return dialog_dir / "messages.json"

    @property
    def history(self) -> FileChatMessageHistory:
        """Lazy-load the FileChatMessageHistory instance."""
        if self._history is None:
            self._history = FileChatMessageHistory(
                file_path=str(self.history_file_path),
                ensure_ascii=False  # Allow non-ASCII characters
            )
        return self._history

    def add_user_message(self, content: str) -> None:
        """Add a user message to the history."""
        self.history.add_user_message(content)

    def add_ai_message(self, content: str) -> None:
        """Add an AI message to the history."""
        self.history.add_ai_message(content)

    def get_messages(self, limit: int | None = None) -> list[BaseMessage]:
        """Get messages from history, optionally limiting to last N messages."""
        messages = self.history.messages
        if limit and len(messages) > limit:
            return messages[-limit:]
        return messages

    def clear(self) -> None:
        """Clear all messages from the history."""
        self.history.clear()
