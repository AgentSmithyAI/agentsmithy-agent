"""Tests for dialog history endpoint."""

import pytest
from fastapi.testclient import TestClient

from agentsmithy_server.api.app import create_app
from agentsmithy_server.core.dialog_reasoning_storage import DialogReasoningStorage
from agentsmithy_server.core.project import Project


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
    assert data["total_messages"] == 2
    assert data["total_reasoning"] == 0
    assert data["total_tool_calls"] == 0

    # Check messages
    msgs = data["messages"]
    assert len(msgs) == 2
    assert msgs[0]["type"] == "human"
    assert msgs[0]["content"] == "Hello"

    assert msgs[1]["type"] == "ai"
    assert msgs[1]["content"] == "Hi there!"


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
    assert data["total_messages"] == 3  # 2 regular + 1 reasoning
    assert data["total_reasoning"] == 1

    # Check that reasoning is embedded in messages
    reasoning_msgs = [m for m in data["messages"] if m["type"] == "reasoning"]
    assert len(reasoning_msgs) == 1

    reasoning = reasoning_msgs[0]
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
    # 2 messages + 1 tool_call event
    assert data["total_messages"] == 3
    assert data["total_tool_calls"] == 1

    # Check tool call event
    tool_events = [m for m in data["messages"] if m["type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool_name"] == "read_file"
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
    # 2 regular + 1 reasoning + 1 tool_call = 4
    assert data["total_messages"] == 4
    assert data["total_reasoning"] == 1
    assert data["total_tool_calls"] == 1

    # Verify all event types are present
    msgs = data["messages"]
    assert len(msgs) == 4
    assert sum(1 for m in msgs if m["type"] == "reasoning") == 1
    assert sum(1 for m in msgs if m["type"] == "tool_call") == 1


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
    msgs = data["messages"]

    # Should have: user + ai + 2 tool_calls
    assert data["total_tool_calls"] == 2

    tool_events = [m for m in msgs if m["type"] == "tool_call"]
    assert len(tool_events) == 2
    assert tool_events[0]["tool_name"] == "read_file"
    assert tool_events[1]["tool_name"] == "write_file"


def test_get_history_empty_dialog(client, test_project):
    """Test getting history for a dialog with no messages."""
    dialog_id = test_project.create_dialog(title="empty", set_current=True)

    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["dialog_id"] == dialog_id
    assert data["total_messages"] == 0
    assert data["total_reasoning"] == 0
    assert data["total_tool_calls"] == 0
    assert len(data["messages"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
