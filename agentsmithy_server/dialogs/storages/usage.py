from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.db import BaseORM, DialogUsageEventORM
from agentsmithy_server.db.base import get_engine, get_session
from agentsmithy_server.dialogs.history import DialogHistory
from agentsmithy_server.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


@dataclass
class DialogUsage:
    dialog_id: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    updated_at: str


class DialogUsageStorage:
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

    def load(self) -> DialogUsage | None:
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                # Return most recent usage event for this dialog
                stmt = (
                    select(DialogUsageEventORM)
                    .where(DialogUsageEventORM.dialog_id == self.dialog_id)
                    .order_by(DialogUsageEventORM.created_at.desc())
                )
                row = session.execute(stmt).scalars().first()
                if not row:
                    return None
                return DialogUsage(
                    dialog_id=row.dialog_id,
                    prompt_tokens=row.prompt_tokens,
                    completion_tokens=row.completion_tokens,
                    total_tokens=row.total_tokens,
                    updated_at=row.created_at,
                )
        except Exception as e:
            agent_logger.error(
                "Failed to load dialog usage", exc_info=True, error=str(e)
            )
            return None

    def upsert(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        model_name: str | None = None,
    ) -> None:
        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()
        try:
            with get_session(engine) as session:
                session.add(
                    DialogUsageEventORM(
                        dialog_id=self.dialog_id,
                        model_name=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        created_at=now,
                    )
                )
                session.commit()
        except Exception as e:
            agent_logger.error(
                "Failed to write dialog usage event", exc_info=True, error=str(e)
            )
