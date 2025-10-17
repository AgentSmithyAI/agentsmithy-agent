"""Storage for file edit events from tool executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.db import BaseORM, DialogFileEditORM
from agentsmithy_server.db.base import get_engine, get_session
from agentsmithy_server.dialogs.history import DialogHistory
from agentsmithy_server.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


@dataclass
class FileEditEvent:
    """A single file edit event."""

    id: int
    dialog_id: str
    file: str
    diff: str | None
    checkpoint: str | None
    created_at: str
    message_index: int


class DialogFileEditStorage:
    """Manages storage of file edit events for a dialog."""

    def __init__(self, project: Project, dialog_id: str, engine: Engine | None = None):
        self.project = project
        self.dialog_id = dialog_id
        self._db_path: Path = DialogHistory(project, dialog_id).db_path
        self._engine: Engine | None = engine

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - dispose resources."""
        self.dispose()
        return False

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine(self._db_path)
        return self._engine

    def dispose(self) -> None:
        """Dispose the database engine and close connections."""
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception:
                pass
            finally:
                self._engine = None

    def __del__(self) -> None:
        """Clean up resources on garbage collection."""
        self.dispose()

    def _ensure_db(self) -> None:
        engine = self._get_engine()
        BaseORM.metadata.create_all(engine)

    def save(
        self,
        file: str,
        diff: str | None = None,
        checkpoint: str | None = None,
        message_index: int = -1,
    ) -> int | None:
        """Save a file edit event.

        Args:
            file: Path to the edited file
            diff: Unified diff content (optional)
            checkpoint: Git commit ID (optional)
            message_index: Index of related message in history

        Returns:
            The ID of the saved event, or None on error
        """
        if not file:
            return None

        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()

        try:
            with get_session(engine) as session:
                edit = DialogFileEditORM(
                    dialog_id=self.dialog_id,
                    file=file,
                    diff=diff,
                    checkpoint=checkpoint,
                    created_at=now,
                    message_index=message_index,
                )
                session.add(edit)
                session.commit()
                session.refresh(edit)
                agent_logger.debug(
                    "Saved file edit event",
                    dialog_id=self.dialog_id,
                    file_edit_id=edit.id,
                    file=file,
                    message_index=message_index,
                )
                return edit.id
        except Exception as e:
            agent_logger.error(
                "Failed to save file edit event", exc_info=True, error=str(e)
            )
            return None

    def get_all(self) -> list[FileEditEvent]:
        """Get all file edit events for this dialog, ordered by creation time."""
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(DialogFileEditORM)
                    .where(DialogFileEditORM.dialog_id == self.dialog_id)
                    .order_by(DialogFileEditORM.created_at)
                )
                rows = session.execute(stmt).scalars().all()
                return [
                    FileEditEvent(
                        id=row.id,
                        dialog_id=row.dialog_id,
                        file=row.file,
                        diff=row.diff,
                        checkpoint=row.checkpoint,
                        created_at=row.created_at,
                        message_index=row.message_index,
                    )
                    for row in rows
                ]
        except Exception as e:
            agent_logger.error(
                "Failed to load file edit events", exc_info=True, error=str(e)
            )
            return []

    def count_all(self) -> int:
        """Count total number of file edit events in the dialog.

        Returns:
            Total count of file edit events
        """
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                from sqlalchemy import func

                stmt = select(func.count(DialogFileEditORM.id)).where(
                    DialogFileEditORM.dialog_id == self.dialog_id
                )
                count = session.execute(stmt).scalar()
                return count or 0
        except Exception as e:
            agent_logger.error(
                "Failed to count file edit events", exc_info=True, error=str(e)
            )
            return 0

    def get_for_indices(self, message_indices: set[int]) -> list[FileEditEvent]:
        """Get file edit events for specific message indices (optimized SQL query).

        Args:
            message_indices: Set of message indices to load edits for

        Returns:
            List of file edit events for the specified indices
        """
        if not message_indices:
            return []

        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(DialogFileEditORM)
                    .where(
                        DialogFileEditORM.dialog_id == self.dialog_id,
                        DialogFileEditORM.message_index.in_(list(message_indices)),
                    )
                    .order_by(DialogFileEditORM.created_at)
                )
                rows = session.execute(stmt).scalars().all()
                return [
                    FileEditEvent(
                        id=row.id,
                        dialog_id=row.dialog_id,
                        file=row.file,
                        diff=row.diff,
                        checkpoint=row.checkpoint,
                        created_at=row.created_at,
                        message_index=row.message_index,
                    )
                    for row in rows
                ]
        except Exception as e:
            agent_logger.error(
                "Failed to load file edits for indices",
                exc_info=True,
                error=str(e),
                indices_count=len(message_indices),
            )
            return []
