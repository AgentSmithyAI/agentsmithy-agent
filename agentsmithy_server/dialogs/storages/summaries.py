from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.db import (
    BaseORM,
    DialogSummaryORM,
)
from agentsmithy_server.db.base import get_engine, get_session
from agentsmithy_server.dialogs.history import DialogHistory
from agentsmithy_server.dialogs.summarization.strategy import KEEP_LAST_MESSAGES
from agentsmithy_server.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


@dataclass
class DialogSummary:
    dialog_id: str
    summary_text: str
    summarized_count: int
    keep_last: int
    updated_at: str
    cutoff_message_index: int | None = None


class DialogSummaryStorage:
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

    def load(self) -> DialogSummary | None:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(DialogSummaryORM)
                    .where(DialogSummaryORM.dialog_id == self.dialog_id)
                    .order_by(DialogSummaryORM.created_at.desc())
                )
                row = session.execute(stmt).scalars().first()
                if not row:
                    return None
                return DialogSummary(
                    dialog_id=row.dialog_id,
                    summary_text=row.summary_text,
                    summarized_count=int(row.summarized_count or 0),
                    keep_last=int(row.keep_last or 0),
                    updated_at=row.created_at,
                    cutoff_message_index=int(row.cutoff_message_index or 0),
                )
        except Exception as e:
            agent_logger.error(
                "Failed to load dialog summary", exc_info=True, error=str(e)
            )
            return None

    def upsert(
        self,
        summary_text: str,
        summarized_count: int,
        keep_last: int | None = None,
    ) -> None:
        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()
        if keep_last is None:
            keep_last = KEEP_LAST_MESSAGES
        try:
            with get_session(engine) as session:
                session.add(
                    DialogSummaryORM(
                        dialog_id=self.dialog_id,
                        cutoff_message_index=int(summarized_count or 0),
                        summary_text=summary_text,
                        keep_last=int(keep_last or 0),
                        created_at=now,
                        summarized_count=int(summarized_count or 0),
                    )
                )
                session.commit()
            agent_logger.info(
                "Updated dialog summary",
                dialog_id=self.dialog_id,
                summarized_count=summarized_count,
                keep_last=keep_last,
                summary_len=len(summary_text or ""),
            )
        except Exception as e:
            agent_logger.error(
                "Failed to upsert dialog summary", exc_info=True, error=str(e)
            )

    def append_version(
        self,
        summary_text: str,
        cutoff_message_index: int,
        keep_last: int | None = None,
    ) -> None:
        """Append a new versioned summary."""
        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()
        if keep_last is None:
            keep_last = KEEP_LAST_MESSAGES
        try:
            with get_session(engine) as session:
                session.add(
                    DialogSummaryORM(
                        dialog_id=self.dialog_id,
                        cutoff_message_index=int(cutoff_message_index or 0),
                        summary_text=summary_text,
                        keep_last=int(keep_last or 0),
                        created_at=now,
                        summarized_count=int(cutoff_message_index or 0),
                    )
                )
                session.commit()
            agent_logger.info(
                "Appended dialog summary version",
                dialog_id=self.dialog_id,
                cutoff_message_index=int(cutoff_message_index or 0),
                keep_last=int(keep_last or 0),
                summary_len=len(summary_text or ""),
            )
        except Exception as e:
            agent_logger.error(
                "Failed to append dialog summary version", exc_info=True, error=str(e)
            )
