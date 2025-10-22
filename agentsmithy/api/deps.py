from __future__ import annotations

import asyncio

from sqlalchemy.engine import Engine

from agentsmithy.core.project import Project, get_current_project
from agentsmithy.db.base import get_engine as _mk_engine
from agentsmithy.services.chat_service import ChatService

# Global chat service instance
_chat_service: ChatService | None = None
_db_engine: Engine | None = None


def get_project() -> Project:
    return get_current_project()


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def set_shutdown_event(event: asyncio.Event) -> None:
    """Set shutdown event on the chat service."""
    service = get_chat_service()
    service.set_shutdown_event(event)


def get_db_engine() -> Engine:
    """Singleton SQLAlchemy Engine bound to the project's dialogs SQLite DB.

    Engine is created on first access and reused.
    """
    global _db_engine
    if _db_engine is None:
        project = get_current_project()
        # Use the inspector-wide journal for global/inspector scope
        db_path = project.dialogs_dir / "journal.sqlite"
        _db_engine = _mk_engine(db_path)
    return _db_engine


def dispose_db_engine() -> None:
    """Dispose the shared Engine if it exists (called on app shutdown)."""
    global _db_engine
    try:
        if _db_engine is not None:
            _db_engine.dispose()
    finally:
        _db_engine = None
