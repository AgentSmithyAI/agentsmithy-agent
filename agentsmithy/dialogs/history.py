"""SQLite-backed dialog history management using LangChain.

Storage layout:
- Inspector: `.agentsmithy/dialogs/journal.sqlite`
- Per dialog: `.agentsmithy/dialogs/<dialog_id>/journal.sqlite`

LangChain's SQLChatMessageHistory still uses `session_id` (the `dialog_id`),
even for per-dialog databases, for compatibility and future-proofing.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict

from agentsmithy.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy.core.project import Project


def _touch_metadata(func: Callable) -> Callable:
    """Decorator to touch dialog metadata after modifying history."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        if self.track_metadata:
            try:
                self.project.upsert_dialog_meta(self.dialog_id)
            except Exception:
                agent_logger.warning(
                    "Failed to update dialog metadata",
                    dialog_id=self.dialog_id,
                    exc_info=True,
                )
        return result

    return wrapper


class DialogHistory:
    """Manages dialog history using SQLite via LangChain's SQLChatMessageHistory."""

    def __init__(self, project: Project, dialog_id: str, track_metadata: bool = True):
        self.project = project
        self.dialog_id = dialog_id
        self.track_metadata = track_metadata
        self._history: SQLChatMessageHistory | None = None
        self._cached_messages: list[BaseMessage] | None = None

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

    @_touch_metadata
    def add_user_message(
        self, content: str, checkpoint: str | None = None, session: str | None = None
    ) -> None:
        """Add a user message to the history.

        Args:
            content: Message content
            checkpoint: Optional checkpoint ID (snapshot before AI response)
            session: Optional session ID
        """
        if checkpoint or session:
            # Use BaseMessage with metadata to include checkpoint and session
            from langchain_core.messages import HumanMessage

            message = HumanMessage(content=content)
            metadata = {}
            if checkpoint:
                metadata["checkpoint"] = checkpoint
            if session:
                metadata["session"] = session
            message.additional_kwargs = metadata
            self.history.add_message(message)
        else:
            self.history.add_user_message(content)
        self._cached_messages = None  # Invalidate cache

    @_touch_metadata
    def add_ai_message(self, content: str | list) -> None:
        """Add an AI message to the history.

        Args:
            content: Message content. Can be:
                - str: Simple text content (OpenAI style)
                - list: Structured content blocks (Anthropic style with thinking)
        """
        from langchain_core.messages import AIMessage

        # Use AIMessage directly to preserve structured content (list of blocks)
        # SQLChatMessageHistory will serialize it properly to JSON
        message = AIMessage(content=content)
        self.history.add_message(message)
        self._cached_messages = None  # Invalidate cache

    @_touch_metadata
    def add_message(self, message: BaseMessage) -> None:
        """Add a generic LangChain BaseMessage to the history."""
        self.history.add_message(message)
        self._cached_messages = None  # Invalidate cache

    @_touch_metadata
    def add_messages(self, messages: Iterable[BaseMessage]) -> None:
        """Add multiple messages atomically where possible."""
        for msg in messages:
            self.history.add_message(msg)
        self._cached_messages = None  # Invalidate cache

    def _get_all_messages(self) -> list[BaseMessage]:
        """Get all messages with caching."""
        if self._cached_messages is None:
            self._cached_messages = self.history.messages
        return self._cached_messages

    def get_messages(self, limit: int | None = None) -> list[BaseMessage]:
        """Get messages from history, optionally limiting to last N messages."""
        messages = self._get_all_messages()
        if limit and len(messages) > limit:
            return messages[-limit:]
        return messages

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None

    def get_messages_count(self) -> int:
        """Get total count of non-empty visible messages via direct SQL.

        Only counts messages that will have idx (non-ToolMessage, non-empty AI).
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                if not self._table_exists(conn, "message_store"):
                    return 0

                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM message_store 
                    WHERE session_id = ? 
                      AND json_extract(message, '$.type') != 'tool'
                      AND NOT (
                          json_extract(message, '$.type') = 'ai' 
                          AND TRIM(COALESCE(json_extract(message, '$.data.content'), '')) = ''
                      )
                    """,
                    (self.dialog_id,),
                )
                count = cursor.fetchone()[0]
                return count
        except Exception:
            # Don't silently fall back - if SQL fails, it's a real problem
            raise

    def count_tool_calls(self) -> int:
        """Count total number of tool calls across all messages.

        Returns:
            Total count of tool calls in the dialog
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                if not self._table_exists(conn, "message_store"):
                    return 0

                cursor = conn.execute(
                    """
                    SELECT SUM(json_array_length(json_extract(message, '$.data.tool_calls')))
                    FROM message_store 
                    WHERE session_id = ? 
                      AND json_extract(message, '$.data.tool_calls') IS NOT NULL
                    """,
                    (self.dialog_id,),
                )
                count = cursor.fetchone()[0]
                return count or 0
        except Exception:
            raise

    def get_messages_slice(
        self, start_index: int | None = None, end_index: int | None = None
    ) -> tuple[list[BaseMessage], list[int], list[int]]:
        """Get a slice of NON-EMPTY visible messages via direct SQL with context.

        This loads non-empty messages based on indices, but also loads nearby empty AI
        messages (before/after) to capture their tool_calls.

        IMPORTANT: When end_index is None (loading last messages), this will load ALL
        trailing empty AI messages to ensure their tool_calls are included in history.

        Args:
            start_index: Starting index in non-empty visible messages.
            end_index: Ending index in non-empty visible messages (exclusive).
                      None means load to end of dialog (including all trailing empty AI).

        Returns:
            Tuple of (messages, original_db_indices, db_ids) where:
            - messages: BaseMessage objects (includes empty AI near the slice)
            - original_db_indices: row numbers in full message list
            - db_ids: actual DB id values (for timestamp ordering)
        """
        if start_index is None:
            start_index = 0

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                if not self._table_exists(conn, "message_store"):
                    return [], [], []

                # Calculate LIMIT and OFFSET for visible messages
                if end_index is None:
                    sql_limit = -1  # No limit in SQLite
                    sql_offset = start_index
                else:
                    sql_limit = end_index - start_index
                    sql_offset = start_index

                # Strategy: Load non-empty messages by indices, then add ALL nearby messages
                # (including empty AI) to get their tool_calls

                # First, get the slice of non-empty messages
                cursor1 = conn.execute(
                    """
                    WITH numbered AS (
                        SELECT 
                            ROW_NUMBER() OVER (ORDER BY id) - 1 as row_num,
                            id, 
                            message,
                            json_extract(message, '$.type') as msg_type,
                            TRIM(COALESCE(json_extract(message, '$.data.content'), '')) as content
                        FROM message_store 
                        WHERE session_id = ?
                    )
                    SELECT row_num, id
                    FROM numbered
                    WHERE msg_type != 'tool' 
                      AND NOT (msg_type = 'ai' AND content = '')
                    ORDER BY row_num
                    LIMIT ? OFFSET ?
                    """,
                    (self.dialog_id, sql_limit, sql_offset),
                )

                non_empty_indices = cursor1.fetchall()

                if not non_empty_indices:
                    return [], [], []

                # Get range of DB row_nums to load (with padding for empty AI)
                min_row_num = non_empty_indices[0][0]
                max_row_num = non_empty_indices[-1][0]

                # Load ALL visible messages in range + trailing empty AI
                # If end_index is None, we're loading the last messages, so include ALL trailing empty AI
                if end_index is None:
                    # Load from min to end of dialog (to capture all trailing empty AI)
                    cursor2 = conn.execute(
                        """
                        WITH numbered AS (
                            SELECT 
                                ROW_NUMBER() OVER (ORDER BY id) - 1 as row_num,
                                id, 
                                message,
                                json_extract(message, '$.type') as msg_type
                            FROM message_store 
                            WHERE session_id = ?
                        )
                        SELECT row_num, id, message 
                        FROM numbered
                        WHERE msg_type != 'tool' AND row_num >= ?
                        ORDER BY row_num
                        """,
                        (self.dialog_id, min_row_num),
                    )
                else:
                    # Paginating in the middle, only load between min and max
                    cursor2 = conn.execute(
                        """
                        WITH numbered AS (
                            SELECT 
                                ROW_NUMBER() OVER (ORDER BY id) - 1 as row_num,
                                id, 
                                message,
                                json_extract(message, '$.type') as msg_type
                            FROM message_store 
                            WHERE session_id = ?
                        )
                        SELECT row_num, id, message 
                        FROM numbered
                        WHERE msg_type != 'tool' AND row_num >= ? AND row_num <= ?
                        ORDER BY row_num
                        """,
                        (self.dialog_id, min_row_num, max_row_num),
                    )

                rows = cursor2.fetchall()

                # Deserialize messages from JSON
                messages = []
                indices = []
                db_ids = []
                for row_num, db_id, message_json in rows:
                    msg_dict = json.loads(message_json)
                    # Convert dict to LangChain message
                    msg_list = messages_from_dict([msg_dict])
                    if msg_list:
                        messages.append(msg_list[0])
                        indices.append(row_num)
                        db_ids.append(db_id)

                return messages, indices, db_ids
        except Exception:
            # Don't silently fall back - if SQL fails, it's a real problem
            raise

    @_touch_metadata
    def clear(self) -> None:
        """Clear all messages from the history."""
        self.history.clear()
        self._cached_messages = None  # Invalidate cache
