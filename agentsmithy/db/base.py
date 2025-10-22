from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def get_engine(db_path: Path) -> Engine:
    """Create a SQLite engine for the given DB path.

    Uses check_same_thread=False to allow access from async contexts.
    Ensures parent directory exists.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+pysqlite:///{db_path}"
    return create_engine(db_url, connect_args={"check_same_thread": False})


@contextmanager
def get_session(engine: Engine) -> Iterator[Session]:
    """Context manager yielding a SQLAlchemy Session bound to engine."""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
