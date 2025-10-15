"""Storage for reasoning/thinking traces from LLM responses.

Reasoning blocks are saved separately from chat history to:
1. Allow analysis of model's thinking process
2. Link reasoning to specific messages via message_index
3. Enable future features like reasoning replay/debugging
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine

from agentsmithy_server.core.dialog_history import DialogHistory
from agentsmithy_server.db import BaseORM, DialogReasoningORM
from agentsmithy_server.db.base import get_engine, get_session
from agentsmithy_server.utils.logger import agent_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.project import Project


@dataclass
class ReasoningBlock:
    """A single reasoning block from the model."""

    id: int
    dialog_id: str
    content: str
    created_at: str
    message_index: int
    model_name: str | None


class DialogReasoningStorage:
    """Manages storage of reasoning traces for a dialog."""

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
        content: str,
        message_index: int = -1,
        model_name: str | None = None,
    ) -> int | None:
        """Save a reasoning block.

        Args:
            content: The reasoning text content
            message_index: Index of the related message in dialog history (-1 if not yet linked)
            model_name: Name of the model that generated this reasoning

        Returns:
            The ID of the saved reasoning block, or None on error
        """
        if not content.strip():
            return None

        self._ensure_db()
        engine = self._get_engine()
        now = datetime.now(UTC).isoformat()

        try:
            with get_session(engine) as session:
                reasoning = DialogReasoningORM(
                    dialog_id=self.dialog_id,
                    content=content,
                    created_at=now,
                    message_index=message_index,
                    model_name=model_name,
                )
                session.add(reasoning)
                session.commit()
                session.refresh(reasoning)
                agent_logger.debug(
                    "Saved reasoning block",
                    dialog_id=self.dialog_id,
                    reasoning_id=reasoning.id,
                    length=len(content),
                    message_index=message_index,
                )
                return reasoning.id
        except Exception as e:
            agent_logger.error(
                "Failed to save reasoning block", exc_info=True, error=str(e)
            )
            return None

    def get_all(self) -> list[ReasoningBlock]:
        """Get all reasoning blocks for this dialog, ordered by creation time."""
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(DialogReasoningORM)
                    .where(DialogReasoningORM.dialog_id == self.dialog_id)
                    .order_by(DialogReasoningORM.created_at)
                )
                rows = session.execute(stmt).scalars().all()
                return [
                    ReasoningBlock(
                        id=row.id,
                        dialog_id=row.dialog_id,
                        content=row.content,
                        created_at=row.created_at,
                        message_index=row.message_index,
                        model_name=row.model_name,
                    )
                    for row in rows
                ]
        except Exception as e:
            agent_logger.error(
                "Failed to load reasoning blocks", exc_info=True, error=str(e)
            )
            return []

    def get_for_message(self, message_index: int) -> list[ReasoningBlock]:
        """Get reasoning blocks linked to a specific message."""
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = (
                    select(DialogReasoningORM)
                    .where(
                        DialogReasoningORM.dialog_id == self.dialog_id,
                        DialogReasoningORM.message_index == message_index,
                    )
                    .order_by(DialogReasoningORM.created_at)
                )
                rows = session.execute(stmt).scalars().all()
                return [
                    ReasoningBlock(
                        id=row.id,
                        dialog_id=row.dialog_id,
                        content=row.content,
                        created_at=row.created_at,
                        message_index=row.message_index,
                        model_name=row.model_name,
                    )
                    for row in rows
                ]
        except Exception as e:
            agent_logger.error(
                "Failed to load reasoning for message",
                exc_info=True,
                error=str(e),
                message_index=message_index,
            )
            return []

    def update_message_index(self, reasoning_id: int, message_index: int) -> bool:
        """Update the message_index for a reasoning block.

        Useful for linking reasoning to messages after the fact.

        Args:
            reasoning_id: ID of the reasoning block
            message_index: New message index to set

        Returns:
            True if successful, False otherwise
        """
        self._ensure_db()
        try:
            engine = self._get_engine()
            with get_session(engine) as session:
                stmt = select(DialogReasoningORM).where(
                    DialogReasoningORM.id == reasoning_id,
                    DialogReasoningORM.dialog_id == self.dialog_id,
                )
                reasoning = session.execute(stmt).scalars().first()
                if reasoning:
                    reasoning.message_index = message_index
                    session.commit()
                    agent_logger.debug(
                        "Updated reasoning message index",
                        reasoning_id=reasoning_id,
                        message_index=message_index,
                    )
                    return True
                return False
        except Exception as e:
            agent_logger.error(
                "Failed to update reasoning message index",
                exc_info=True,
                error=str(e),
                reasoning_id=reasoning_id,
            )
            return False

