"""Tests for session field in SSE events."""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.core.project import Project
from agentsmithy.domain.events import EventFactory


def test_user_event_includes_session():
    """Test that UserEvent includes session field."""
    event = EventFactory.user(
        content="Test message",
        checkpoint="abc123",
        session="session_2",
        dialog_id="dialog123",
    )

    assert event.checkpoint == "abc123"
    assert event.session == "session_2"
    assert event.content == "Test message"

    # Test conversion to dict
    event_dict = event.to_dict()
    assert event_dict["checkpoint"] == "abc123"
    assert event_dict["session"] == "session_2"


def test_user_event_session_optional():
    """Test that session is optional in UserEvent."""
    event = EventFactory.user(
        content="Test message", checkpoint="abc123", dialog_id="dialog123"
    )

    assert event.checkpoint == "abc123"
    assert event.session is None

    # Test conversion to dict
    event_dict = event.to_dict()
    assert event_dict["checkpoint"] == "abc123"
    assert "session" not in event_dict  # None values are filtered out


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


def test_user_message_saved_with_session(temp_project):
    """Test that user message is saved with session in history."""
    dialog_id = temp_project.create_dialog(title="Test Session", set_current=True)

    # Add user message with checkpoint and session
    history = temp_project.get_dialog_history(dialog_id)
    history.add_user_message(
        "Test query", checkpoint="checkpoint_abc", session="session_1"
    )

    # Retrieve messages
    messages = history.get_messages()
    assert len(messages) == 1

    user_msg = messages[0]
    assert user_msg.content == "Test query"

    # Check additional_kwargs contains both checkpoint and session
    additional_kwargs = getattr(user_msg, "additional_kwargs", {})
    assert additional_kwargs.get("checkpoint") == "checkpoint_abc"
    assert additional_kwargs.get("session") == "session_1"
