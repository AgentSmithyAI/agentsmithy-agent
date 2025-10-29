"""Integration test for checkpoint SSE events."""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.core.project import Project
from agentsmithy.domain.events import EventFactory, EventType


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


def test_user_event_factory_includes_checkpoint():
    """Test that UserEvent factory creates events with checkpoint."""
    event = EventFactory.user(
        content="Test message", checkpoint="abc123def456", dialog_id="test-dialog"
    )

    assert event.type == EventType.USER
    assert event.content == "Test message"
    assert event.checkpoint == "abc123def456"
    assert event.dialog_id == "test-dialog"

    # Test SSE serialization
    sse = event.to_sse()
    assert "data" in sse

    import json

    data = json.loads(sse["data"])
    assert data["type"] == "user"
    assert data["content"] == "Test message"
    assert data["checkpoint"] == "abc123def456"
    assert data["dialog_id"] == "test-dialog"


def test_user_message_saved_with_checkpoint(temp_project):
    """Test that user message is saved to history with checkpoint metadata."""
    from agentsmithy.services.versioning import VersioningTracker

    dialog_id = temp_project.create_dialog(title="Test Dialog")

    # Create a checkpoint
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    checkpoint = tracker.create_checkpoint("Test checkpoint")

    # Add user message with checkpoint
    history = temp_project.get_dialog_history(dialog_id)
    history.add_user_message("User query", checkpoint=checkpoint.commit_id)

    # Verify message was saved with checkpoint
    messages = history.get_messages()
    user_messages = [m for m in messages if m.type == "human"]

    assert len(user_messages) > 0
    user_msg = user_messages[-1]
    assert user_msg.content == "User query"

    # Check checkpoint in metadata
    checkpoint_in_msg = getattr(user_msg, "additional_kwargs", {}).get("checkpoint")
    assert checkpoint_in_msg == checkpoint.commit_id
