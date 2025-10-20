"""Tests for dialog history with empty dialogs (no message_store table yet)."""

import sqlite3

import pytest

from agentsmithy_server.core.project import Project
from agentsmithy_server.dialogs.history import DialogHistory


@pytest.fixture
def empty_dialog_project(tmp_path):
    """Create a project with a dialog that has no messages yet."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    state_dir = project_root / ".agentsmithy"
    project = Project(name="test_project", root=project_root, state_dir=state_dir)
    project.ensure_state_dir()

    # Create dialog directory but no message_store table
    dialog_id = "test_dialog_empty"
    dialog_dir = project.get_dialog_dir(dialog_id)
    dialog_dir.mkdir(parents=True, exist_ok=True)

    # Create empty database file (simulates fresh dialog)
    db_path = dialog_dir / "journal.sqlite"
    conn = sqlite3.connect(str(db_path))
    # Create other tables but NOT message_store
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_results (
            tool_call_id TEXT PRIMARY KEY,
            dialog_id TEXT,
            tool_name TEXT
        )
    """
    )
    conn.commit()
    conn.close()

    return project, dialog_id


def test_table_exists_returns_false_for_missing_table(empty_dialog_project):
    """Test _table_exists returns False when table doesn't exist."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    with sqlite3.connect(str(history.db_path)) as conn:
        assert history._table_exists(conn, "message_store") is False
        assert history._table_exists(conn, "tool_results") is True


def test_table_exists_returns_true_for_existing_table(empty_dialog_project):
    """Test _table_exists returns True when table exists."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    # Create message_store table
    with sqlite3.connect(str(history.db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE message_store (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                message TEXT
            )
        """
        )
        conn.commit()

        assert history._table_exists(conn, "message_store") is True


def test_get_messages_count_returns_zero_for_empty_dialog(empty_dialog_project):
    """Test get_messages_count returns 0 when message_store doesn't exist."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    count = history.get_messages_count()
    assert count == 0


def test_count_tool_calls_returns_zero_for_empty_dialog(empty_dialog_project):
    """Test count_tool_calls returns 0 when message_store doesn't exist."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    count = history.count_tool_calls()
    assert count == 0


def test_get_messages_slice_returns_empty_for_empty_dialog(empty_dialog_project):
    """Test get_messages_slice returns empty lists when message_store doesn't exist."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    messages, indices, db_ids = history.get_messages_slice()

    assert messages == []
    assert indices == []
    assert db_ids == []


def test_get_messages_slice_with_params_returns_empty(empty_dialog_project):
    """Test get_messages_slice with parameters returns empty lists when table missing."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    messages, indices, db_ids = history.get_messages_slice(start_index=0, end_index=10)

    assert messages == []
    assert indices == []
    assert db_ids == []


def test_methods_work_after_table_created(empty_dialog_project):
    """Test that methods work correctly after message_store is created."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    # Initially should return empty/zero
    assert history.get_messages_count() == 0

    # Add a message (this creates message_store through LangChain)
    history.add_user_message("test message")

    # Now should return 1
    assert history.get_messages_count() == 1

    messages, indices, db_ids = history.get_messages_slice()
    assert len(messages) == 1
    assert messages[0].content == "test message"


def test_completely_missing_database_file(tmp_path):
    """Test behavior when database file doesn't exist at all (but directory exists)."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    state_dir = project_root / ".agentsmithy"
    project = Project(name="test_project", root=project_root, state_dir=state_dir)
    project.ensure_state_dir()

    dialog_id = "nonexistent_dialog"
    # Create dialog directory (simulates dialog creation) but no DB file yet
    dialog_dir = project.get_dialog_dir(dialog_id)
    dialog_dir.mkdir(parents=True, exist_ok=True)

    # Create empty DB file
    db_path = dialog_dir / "journal.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.close()

    history = DialogHistory(project, dialog_id)

    # Should not raise errors, just return empty/zero
    assert history.get_messages_count() == 0
    assert history.count_tool_calls() == 0

    messages, indices, db_ids = history.get_messages_slice()
    assert messages == []
    assert indices == []
    assert db_ids == []


def test_sql_error_is_raised_for_other_errors(empty_dialog_project):
    """Test that non-table-missing errors are still raised."""
    project, dialog_id = empty_dialog_project
    history = DialogHistory(project, dialog_id)

    # Create message_store with wrong schema to cause SQL errors
    with sqlite3.connect(str(history.db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE message_store (
                id INTEGER PRIMARY KEY
                -- Missing required columns
            )
        """
        )
        conn.commit()

    # Should raise an error (not silently return 0)
    with pytest.raises(sqlite3.OperationalError):
        history.get_messages_count()
