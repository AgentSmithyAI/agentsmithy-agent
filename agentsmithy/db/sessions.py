"""Session management for dialog approval workflow."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agentsmithy.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger("db.sessions")


def ensure_sessions_tables(db_path: Path) -> None:
    """Ensure sessions and dialog_branches tables exist in the database.

    Args:
        db_path: Path to the SQLite database file
    """
    with sqlite3.connect(str(db_path)) as conn:
        # Create sessions table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT UNIQUE,
                ref_name TEXT,
                status TEXT,
                created_at TEXT,
                closed_at TEXT,
                approved_commit TEXT,
                checkpoints_count INTEGER DEFAULT 0,
                branch_exists INTEGER DEFAULT 1
            )
        """
        )

        # Create index on status
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions(status)
        """
        )

        # Create dialog_branches table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dialog_branches (
                branch_type TEXT PRIMARY KEY,
                ref_name TEXT,
                head_commit TEXT,
                valid INTEGER DEFAULT 1
            )
        """
        )

        conn.commit()


def create_initial_session(db_path: Path, session_name: str = "session_1") -> None:
    """Create the initial active session in the database.

    Args:
        db_path: Path to the SQLite database file
        session_name: Name of the session (default: session_1)
    """
    ensure_sessions_tables(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        # Check if session already exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE session_name = ?", (session_name,)
        )
        if cursor.fetchone()[0] > 0:
            return

        # Insert initial session
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO sessions 
            (session_name, ref_name, status, created_at, checkpoints_count, branch_exists)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (session_name, f"refs/heads/{session_name}", "active", now, 0, 1),
        )

        # Initialize dialog_branches
        conn.execute(
            """
            INSERT OR REPLACE INTO dialog_branches (branch_type, ref_name, valid)
            VALUES (?, ?, ?)
        """,
            ("main", "refs/heads/main", 1),
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO dialog_branches (branch_type, ref_name, valid)
            VALUES (?, ?, ?)
        """,
            ("session", f"refs/heads/{session_name}", 1),
        )

        conn.commit()


def get_active_session(db_path: Path) -> str | None:
    """Get the name of the active session.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Session name or None if no active session
    """
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(
                "SELECT session_name FROM sessions WHERE status = 'active' LIMIT 1"
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def close_session(
    db_path: Path, session_name: str, status: str, approved_commit: str | None = None
) -> None:
    """Mark a session as closed (merged or abandoned).

    Args:
        db_path: Path to the SQLite database file
        session_name: Name of the session to close
        status: New status ("merged" or "abandoned")
        approved_commit: Merge commit ID (for merged sessions)
    """
    now = datetime.utcnow().isoformat()

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            UPDATE sessions 
            SET status = ?, closed_at = ?, approved_commit = ?
            WHERE session_name = ?
        """,
            (status, now, approved_commit, session_name),
        )
        conn.commit()


def create_new_session(db_path: Path, session_name: str) -> None:
    """Create a new active session.

    Args:
        db_path: Path to the SQLite database file
        session_name: Name of the new session
    """
    now = datetime.utcnow().isoformat()

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO sessions 
            (session_name, ref_name, status, created_at, checkpoints_count, branch_exists)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (session_name, f"refs/heads/{session_name}", "active", now, 0, 1),
        )

        # Update dialog_branches to point to new session
        conn.execute(
            """
            UPDATE dialog_branches 
            SET ref_name = ?
            WHERE branch_type = 'session'
        """,
            (f"refs/heads/{session_name}",),
        )

        conn.commit()


def update_branch_head(db_path: Path, branch_type: str, head_commit: str) -> None:
    """Update the head commit for a branch.

    Args:
        db_path: Path to the SQLite database file
        branch_type: "main" or "session"
        head_commit: New head commit ID
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            UPDATE dialog_branches 
            SET head_commit = ?
            WHERE branch_type = ?
        """,
            (head_commit, branch_type),
        )
        conn.commit()


def increment_checkpoints_count(db_path: Path, session_name: str) -> None:
    """Increment the checkpoints count for a session.

    Args:
        db_path: Path to the SQLite database file
        session_name: Name of the session
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            UPDATE sessions 
            SET checkpoints_count = checkpoints_count + 1
            WHERE session_name = ?
        """,
            (session_name,),
        )
        conn.commit()
