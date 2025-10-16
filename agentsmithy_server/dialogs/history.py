"""SQLite-backed dialog history management using LangChain.

Storage layout:
- Inspector: `.agentsmithy/dialogs/journal.sqlite`
- Per dialog: `.agentsmithy/dialogs/<dialog_id>/journal.sqlite`

LangChain's SQLChatMessageHistory still uses `session_id` (the `dialog_id`),
even for per-dialog databases, for compatibility and future-proofing.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import BaseMessage

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


class DialogHistory:
    """Manages dialog history using SQLite via LangChain's SQLChatMessageHistory."""

    def __init__(self, project: Project, dialog_id: str):
        self.project = project
        self.dialog_id = dialog_id
        self._history: SQLChatMessageHistory | None = None

    @property
    def db_path(self) -> Path:
        """Get the SQLite DB path based on dialog scope.

        - For the special inspector scope (dialog_id == "inspector"), use a
          shared file under the dialogs root: `journal.sqlite`.
        - For regular dialogs, store the database inside the dialog's own
          directory: `<dialogs>/<dialog_id>/journal.sqlite`.
        """
        dialogs_root = self.project.dialogs_dir
        dialogs_root.mkdir(parents=True, exist_ok=True)
        if self.dialog_id == "inspector":
            return dialogs_root / "journal.sqlite"
        return self.project.get_dialog_dir(self.dialog_id) / "journal.sqlite"

    @property
    def history(self) -> SQLChatMessageHistory:
        """Lazy-load the SQLChatMessageHistory instance bound to dialog_id."""
        if self._history is None:
            # Ensure parent dir exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Construct SQLite URL; use absolute path
            db_url = f"sqlite:///{self.db_path}"

            # LangChain 0.2.2+ uses `connection` (connection_string was deprecated).
            self._history = SQLChatMessageHistory(
                session_id=self.dialog_id,
                connection=db_url,
            )
        return self._history

    def add_user_message(self, content: str) -> None:
        """Add a user message to the history."""
        self.history.add_user_message(content)
        # Touch dialog metadata updated_at
        try:
            self.project.upsert_dialog_meta(self.dialog_id)
        except Exception:
            pass

    def add_ai_message(self, content: str) -> None:
        """Add an AI message to the history."""
        self.history.add_ai_message(content)
        # Touch dialog metadata updated_at
        try:
            self.project.upsert_dialog_meta(self.dialog_id)
        except Exception:
            pass

    def add_message(self, message: BaseMessage) -> None:
        """Add a generic LangChain BaseMessage to the history."""
        self.history.add_message(message)
        try:
            self.project.upsert_dialog_meta(self.dialog_id)
        except Exception:
            pass

    def add_messages(self, messages: Iterable[BaseMessage]) -> None:
        """Add multiple messages atomically where possible."""
        for msg in messages:
            self.history.add_message(msg)
        try:
            self.project.upsert_dialog_meta(self.dialog_id)
        except Exception:
            pass

    def get_messages(self, limit: int | None = None) -> list[BaseMessage]:
        """Get messages from history, optionally limiting to last N messages."""
        messages = self.history.messages
        if limit and len(messages) > limit:
            return messages[-limit:]
        return messages

    def clear(self) -> None:
        """Clear all messages from the history."""
        self.history.clear()
        try:
            self.project.upsert_dialog_meta(self.dialog_id)
        except Exception:
            pass
