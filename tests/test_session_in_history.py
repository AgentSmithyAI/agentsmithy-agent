"""Tests for session field in history endpoint."""

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


def test_history_includes_session_in_user_messages(client, temp_project):
    """Test that history endpoint includes session in user messages."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test History", set_current=True)

    # Add user messages with checkpoints and sessions
    history = temp_project.get_dialog_history(dialog_id)
    history.add_user_message(
        "First message", checkpoint="checkpoint_1", session="session_1"
    )
    history.add_ai_message("AI response 1")

    history.add_user_message(
        "Second message", checkpoint="checkpoint_2", session="session_1"
    )
    history.add_ai_message("AI response 2")

    # Get history via API
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    events = data["events"]

    # Find user messages
    user_events = [e for e in events if e["type"] == "user"]
    assert len(user_events) == 2

    # Check first user message
    assert user_events[0]["content"] == "First message"
    assert user_events[0]["checkpoint"] == "checkpoint_1"
    assert user_events[0]["session"] == "session_1"

    # Check second user message
    assert user_events[1]["content"] == "Second message"
    assert user_events[1]["checkpoint"] == "checkpoint_2"
    assert user_events[1]["session"] == "session_1"


def test_history_session_tracks_approve_cycles(client, temp_project):
    """Test that session changes are visible in history after approve."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Cycles", set_current=True)
    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Session 1
    history = temp_project.get_dialog_history(dialog_id)
    test_file = temp_project.root / "test.txt"
    test_file.write_text("V1")
    checkpoint1 = tracker.create_checkpoint("Change 1")
    history.add_user_message(
        "Change 1", checkpoint=checkpoint1.commit_id, session="session_1"
    )
    history.add_ai_message("Done")

    # Approve -> session_2
    tracker.approve_all()

    # Session 2
    test_file.write_text("V2")
    checkpoint2 = tracker.create_checkpoint("Change 2")
    history.add_user_message(
        "Change 2", checkpoint=checkpoint2.commit_id, session="session_2"
    )
    history.add_ai_message("Done")

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    events = response.json()["events"]
    user_events = [e for e in events if e["type"] == "user"]

    # First message in session_1
    assert user_events[0]["session"] == "session_1"

    # Second message in session_2
    assert user_events[1]["session"] == "session_2"


def test_history_session_null_when_not_set(client, temp_project):
    """Test that session is null when not explicitly set."""
    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Null", set_current=True)

    # Add user message without session
    history = temp_project.get_dialog_history(dialog_id)
    history.add_user_message("Message without session", checkpoint="checkpoint_abc")

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    events = response.json()["events"]
    user_events = [e for e in events if e["type"] == "user"]

    assert len(user_events) == 1
    assert user_events[0]["checkpoint"] == "checkpoint_abc"
    # Session should not be present in response if it's None
    assert user_events[0].get("session") is None
