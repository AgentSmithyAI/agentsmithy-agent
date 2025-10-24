"""Tests for approve/reset API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import set_workspace
from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        workspace = set_workspace(project_root)
        project = workspace.get_project("test")
        project.ensure_state_dir()
        project.ensure_dialogs_dir()
        yield project


@pytest.fixture
def client(temp_project):
    """Create test client with project dependency override."""
    from agentsmithy.api.deps import get_project

    app = create_app()

    # Override get_project dependency
    def override_get_project():
        return temp_project

    app.dependency_overrides[get_project] = override_get_project

    return TestClient(app)


def test_approve_endpoint(client, temp_project):
    """Test POST /dialogs/{id}/approve endpoint."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Approve", set_current=True)

    # Create some checkpoints
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Content 1")
    tracker.create_checkpoint("Checkpoint 1")
    test_file.write_text("Content 2")
    tracker.create_checkpoint("Checkpoint 2")

    # Approve session
    response = client.post(
        f"/api/dialogs/{dialog_id}/approve", json={"message": "Test approval"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "approved_commit" in data
    assert "new_session" in data
    assert "commits_approved" in data
    assert data["new_session"] == "session_2"
    assert data["commits_approved"] > 0


def test_reset_endpoint(client, temp_project):
    """Test POST /dialogs/{id}/reset endpoint."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Reset", set_current=True)

    # Create and approve session
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Approved")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all()

    # Make changes in new session
    test_file.write_text("Unapproved")
    tracker.create_checkpoint("Checkpoint 2")

    # Reset to approved
    response = client.post(f"/api/dialogs/{dialog_id}/reset")

    assert response.status_code == 200
    data = response.json()

    assert "reset_to" in data
    assert "new_session" in data
    assert data["new_session"] == "session_3"

    # Verify file was restored
    assert test_file.read_text() == "Approved"


def test_approve_empty_session(client, temp_project):
    """Test approving session with no changes."""
    # Create dialog (empty)
    dialog_id = temp_project.create_dialog(title="Empty", set_current=True)

    # Approve immediately
    response = client.post(
        f"/api/dialogs/{dialog_id}/approve", json={"message": "Empty approval"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["commits_approved"] == 0
    assert data["new_session"] == "session_2"


def test_multiple_approve_reset_cycles(client, temp_project):
    """Test multiple approve/reset cycles."""
    dialog_id = temp_project.create_dialog(title="Cycles", set_current=True)
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    test_file = temp_project.root / "test.txt"

    # Cycle 1: work -> approve
    test_file.write_text("V1")
    tracker.create_checkpoint("V1")
    response = client.post(f"/api/dialogs/{dialog_id}/approve")
    assert response.status_code == 200
    assert response.json()["new_session"] == "session_2"

    # Cycle 2: work -> reset
    test_file.write_text("V2")
    tracker.create_checkpoint("V2")
    response = client.post(f"/api/dialogs/{dialog_id}/reset")
    assert response.status_code == 200
    assert response.json()["new_session"] == "session_3"
    assert test_file.read_text() == "V1"  # Reset to approved

    # Cycle 3: work -> approve
    test_file.write_text("V3")
    tracker.create_checkpoint("V3")
    response = client.post(f"/api/dialogs/{dialog_id}/approve")
    assert response.status_code == 200
    assert response.json()["new_session"] == "session_4"
    assert test_file.read_text() == "V3"  # Approved stays


def test_get_session_status(client, temp_project):
    """Test GET /dialogs/{id}/session endpoint."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Session", set_current=True)

    # Get initial session status (no unapproved changes)
    response = client.get(f"/api/dialogs/{dialog_id}/session")
    assert response.status_code == 200
    data = response.json()

    assert data["active_session"] is None  # No active session when nothing unapproved
    assert data["session_ref"] is None
    assert not data["has_unapproved"]
    assert "last_approved_at" in data

    # Create checkpoint (makes session unapproved)
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    test_file = temp_project.root / "test.txt"
    test_file.write_text("New content")
    tracker.create_checkpoint("Change")

    # Check session status again (now has active session)
    response = client.get(f"/api/dialogs/{dialog_id}/session")
    assert response.status_code == 200
    data = response.json()

    assert data["active_session"] == "session_1"
    assert data["session_ref"] == "refs/heads/session_1"
    assert data["has_unapproved"]  # Now has unapproved changes

    # Approve
    client.post(f"/api/dialogs/{dialog_id}/approve")

    # Check session status after approve (no unapproved again)
    response = client.get(f"/api/dialogs/{dialog_id}/session")
    assert response.status_code == 200
    data = response.json()

    assert data["active_session"] is None  # No active session after approve
    assert data["session_ref"] is None
    assert not data["has_unapproved"]
