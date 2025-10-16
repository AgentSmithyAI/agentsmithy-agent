"""Tests for dialog history endpoint."""

import pytest
from fastapi.testclient import TestClient

from agentsmithy_server.api.app import create_app
from agentsmithy_server.core.project import Project
from agentsmithy_server.dialogs.storages.reasoning import DialogReasoningStorage


@pytest.fixture
def test_project(tmp_path):
    """Create a test project."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"
    return Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )


@pytest.fixture
def client(test_project, monkeypatch):
    """Create test client with mocked project."""

    def mock_get_current_project():
        return test_project

    monkeypatch.setattr(
        "agentsmithy_server.core.project.get_current_project",
        mock_get_current_project,
    )
    monkeypatch.setattr(
        "agentsmithy_server.api.deps.get_current_project",
        mock_get_current_project,
    )

    app = create_app()
    return TestClient(app)


def test_get_history_for_nonexistent_dialog(client, test_project):
    """Test getting history for a dialog that doesn't exist."""
    response = client.get("/api/dialogs/nonexistent_id/history")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_history_with_messages_only(client, test_project):
    """Test getting history with only messages (no reasoning or tool calls)."""
    # Create a dialog and add messages
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    history.add_user_message("Hello")
    history.add_ai_message("Hi there!")

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["dialog_id"] == dialog_id

    # Check events
    events = data["events"]
    assert len(events) == 2
    assert events[0]["type"] == "user"
    assert events[0]["content"] == "Hello"

    assert events[1]["type"] == "chat"
    assert events[1]["content"] == "Hi there!"


def test_get_history_with_reasoning(client, test_project):
    """Test getting history with reasoning blocks."""
    # Create dialog with messages
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    history.add_user_message("Analyze this")
    history.add_ai_message("I'll analyze it")

    # Add reasoning block
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="First, I need to understand the context...",
            message_index=1,
            model_name="gpt-4o",
        )

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()

    # Check that reasoning is in events
    events = data["events"]
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1

    reasoning = reasoning_events[0]
    assert reasoning["content"] == "First, I need to understand the context..."
    assert reasoning["model_name"] == "gpt-4o"


def test_get_history_with_tool_calls(client, test_project):
    """Test getting history with tool calls as events."""
    from langchain_core.messages import AIMessage

    # Create dialog with messages
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    history.add_user_message("Read file.txt")

    # Add AI message with tool call
    ai_msg = AIMessage(
        content="I'll read it",
        tool_calls=[
            {"id": "call_123", "name": "read_file", "args": {"path": "file.txt"}}
        ],
    )
    history.add_message(ai_msg)

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()

    # Check tool call event
    events = data["events"]
    tool_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "read_file"
    assert tool_events[0]["args"] == {"path": "file.txt"}


def test_get_history_complete(client, test_project):
    """Test getting complete history with messages, reasoning, and tool calls."""
    from langchain_core.messages import AIMessage

    # Create dialog
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add messages
    history.add_user_message("Do something")

    # Add AI with tool call
    ai_msg = AIMessage(
        content="I'll do it",
        tool_calls=[
            {"id": "call_1", "name": "write_file", "args": {"path": "output.txt"}}
        ],
    )
    history.add_message(ai_msg)

    # Add reasoning
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Thinking about the best approach...",
            message_index=1,
            model_name="gpt-4o",
        )

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["dialog_id"] == dialog_id

    # Verify all event types are present
    events = data["events"]
    assert sum(1 for e in events if e["type"] == "reasoning") == 1
    assert sum(1 for e in events if e["type"] == "tool_call") == 1
    assert sum(1 for e in events if e["type"] == "chat") >= 1
    assert sum(1 for e in events if e["type"] == "user") >= 1


def test_get_history_with_tool_calls_ordering(client, test_project):
    """Test that tool calls appear in correct order in event stream."""
    from langchain_core.messages import AIMessage

    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    history.add_user_message("Do two things")

    ai_msg = AIMessage(
        content="I'll do both",
        tool_calls=[
            {"id": "call_1", "name": "read_file", "args": {"path": "a.txt"}},
            {"id": "call_2", "name": "write_file", "args": {"path": "b.txt"}},
        ],
    )
    history.add_message(ai_msg)

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    events = data["events"]

    # Should have 2 tool_call events
    tool_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_events) == 2
    assert tool_events[0]["name"] == "read_file"
    assert tool_events[1]["name"] == "write_file"


def test_get_history_empty_dialog(client, test_project):
    """Test getting history for a dialog with no messages."""
    dialog_id = test_project.create_dialog(title="empty", set_current=True)

    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["dialog_id"] == dialog_id
    assert len(data["events"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
