"""Tests for session approval workflow."""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.core.project import Project
from agentsmithy.db.sessions import (
    get_active_session,
)
from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        state_dir = project_root / ".agentsmithy"
        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()
        project.ensure_dialogs_dir()
        yield project


@pytest.fixture
def dialog_with_session(temp_project):
    """Create dialog with initialized session."""
    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)
    yield temp_project, dialog_id


def test_create_dialog_initializes_session(dialog_with_session):
    """Test that creating dialog initializes session_1."""
    project, dialog_id = dialog_with_session

    # Check session was created in database
    db_path = project.get_dialog_dir(dialog_id) / "journal.sqlite"
    assert db_path.exists()

    active_session = get_active_session(db_path)
    assert active_session == "session_1"

    # Check metadata has session info
    index = project.load_dialogs_index()
    dialog_meta = None
    for d in index.get("dialogs", []):
        if d["id"] == dialog_id:
            dialog_meta = d
            break

    assert dialog_meta is not None
    assert dialog_meta.get("active_session") == "session_1"
    assert "last_approved_at" in dialog_meta


def test_approve_session_workflow(dialog_with_session):
    """Test full approve session workflow."""
    project, dialog_id = dialog_with_session

    tracker = VersioningTracker(str(project.root), dialog_id)

    # Create some checkpoints in session_1
    test_file = project.root / "test1.txt"
    test_file.write_text("Content 1")
    tracker.create_checkpoint("Checkpoint 1")

    test_file.write_text("Content 2")
    tracker.create_checkpoint("Checkpoint 2")

    # Approve session
    result = tracker.approve_all(message="Test approval")

    assert result["commits_approved"] > 0
    assert result["new_session"] == "session_2"
    assert "approved_commit" in result

    # Check database was updated
    db_path = project.get_dialog_dir(dialog_id) / "journal.sqlite"
    active_session = get_active_session(db_path)
    assert active_session == "session_2"


def test_reset_to_approved_workflow(dialog_with_session):
    """Test reset to approved workflow."""
    project, dialog_id = dialog_with_session

    tracker = VersioningTracker(str(project.root), dialog_id)

    # Create and approve first session
    test_file = project.root / "test1.txt"
    test_file.write_text("Approved content")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all(message="Approve session 1")

    # Make changes in session_2
    test_file.write_text("New unapproved content")
    tracker.create_checkpoint("Checkpoint 2")

    # Reset to approved
    result = tracker.reset_to_approved()

    assert result["new_session"] == "session_3"
    assert "reset_to" in result

    # Manually restore files (this is normally done by the API endpoint)
    tracker.restore_checkpoint(result["reset_to"])

    # Check file was restored
    assert test_file.read_text() == "Approved content"

    # Check database was updated
    db_path = project.get_dialog_dir(dialog_id) / "journal.sqlite"
    active_session = get_active_session(db_path)
    assert active_session == "session_3"


def test_approve_with_no_changes(dialog_with_session):
    """Test approve when session has no new changes."""
    project, dialog_id = dialog_with_session

    tracker = VersioningTracker(str(project.root), dialog_id)

    # Approve empty session
    result = tracker.approve_all(message="Empty approval")

    assert result["commits_approved"] == 0
    assert result["new_session"] == "session_2"


def test_multiple_approve_cycles(dialog_with_session):
    """Test multiple approve/work cycles."""
    project, dialog_id = dialog_with_session

    tracker = VersioningTracker(str(project.root), dialog_id)
    test_file = project.root / "test.txt"

    # Cycle 1
    test_file.write_text("V1")
    tracker.create_checkpoint("V1")
    result1 = tracker.approve_all()
    assert result1["new_session"] == "session_2"

    # Cycle 2
    test_file.write_text("V2")
    tracker.create_checkpoint("V2")
    result2 = tracker.approve_all()
    assert result2["new_session"] == "session_3"

    # Cycle 3
    test_file.write_text("V3")
    tracker.create_checkpoint("V3")
    result3 = tracker.approve_all()
    assert result3["new_session"] == "session_4"

    # Verify file has final content
    assert test_file.read_text() == "V3"
