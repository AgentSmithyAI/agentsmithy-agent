from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.core.dialog_history import DialogHistory
from agentsmithy_server.core.summarization.strategy import KEEP_LAST_MESSAGES
from agentsmithy_server.db import BaseORM, DialogSummaryORM
from agentsmithy_server.db.base import get_engine, get_session
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


class DialogSummaryStorage:
    def __init__(self, project: Project, dialog_id: str, engine: Engine | None = None):
        self.project = project
        self.dialog_id = dialog_id
        self._db_path: Path = DialogHistory(project, dialog_id).db_path
        self._engine: Engine | None = engine

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine(self._db_path)
        return self._engine

    def _ensure_db(self) -> None:
        engine = self._get_engine()
        BaseORM.metadata.create_all(engine)

    def load(self) -> DialogSummary | None:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = select(DialogSummaryORM).where(
                    DialogSummaryORM.dialog_id == self.dialog_id
                )
                row = session.execute(stmt).scalar_one_or_none()
                if not row:
                    return None
                return DialogSummary(
                    dialog_id=row.dialog_id,
                    summary_text=row.summary_text,
                    summarized_count=int(row.summarized_count or 0),
                    keep_last=int(row.keep_last or 0),
                    updated_at=row.updated_at,
                )
        except Exception as e:
            agent_logger.error("Failed to load dialog summary", exception=e)
            return None

    def upsert(
        self, summary_text: str, summarized_count: int, keep_last: int | None = None
    ) -> None:
        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()
        if keep_last is None:
            keep_last = KEEP_LAST_MESSAGES
        try:
            with get_session(engine) as session:
                session.merge(
                    DialogSummaryORM(
                        dialog_id=self.dialog_id,
                        summary_text=summary_text,
                        summarized_count=summarized_count,
                        keep_last=keep_last,
                        updated_at=now,
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
            agent_logger.error("Failed to upsert dialog summary", exception=e)
