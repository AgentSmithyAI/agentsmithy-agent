"""Tests for dialog history endpoint."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agentsmithy_server.api.app import create_app
from agentsmithy_server.core.dialog_reasoning_storage import DialogReasoningStorage
from agentsmithy_server.core.project import Project
from agentsmithy_server.core.tool_results_storage import ToolResultsStorage


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
    assert len(data["messages"]) == 2
    assert data["messages"][0]["type"] == "human"
    assert data["messages"][0]["content"] == "Hello"
    assert data["messages"][0]["index"] == 0

    assert data["messages"][1]["type"] == "ai"
    assert data["messages"][1]["content"] == "Hi there!"
    assert data["messages"][1]["index"] == 1


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
    assert "timestamp" in reasoning
    assert reasoning["reasoning_id"] == 1


def test_get_history_with_tool_calls(client, test_project):
    """Test getting history with tool calls."""
    # Create dialog with messages
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    history.add_user_message("Read file.txt")
    history.add_ai_message("I'll read it")

    # Add tool call result using async API
    async def add_tool_result():
        with ToolResultsStorage(test_project, dialog_id) as storage:
            await storage.store_result(
                tool_call_id="call_123",
                tool_name="read_file",
                args={"path": "file.txt"},
                result={"content": "File content here"},
            )

    asyncio.run(add_tool_result())

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["total_messages"] == 2
    assert data["total_tool_calls"] == 1

    # Check tool call
    tool_call = data["tool_calls"][0]
    assert tool_call["tool_call_id"] == "call_123"
    assert tool_call["tool_name"] == "read_file"
    # args are not included in metadata list (would need separate query)
    assert "result_preview" in tool_call
    assert tool_call["has_full_result"] is True


def test_get_history_complete(client, test_project):
    """Test getting complete history with messages, reasoning, and tool calls."""
    # Create dialog
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add messages
    history.add_user_message("Do something")
    history.add_ai_message("I'll do it")

    # Add reasoning
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Thinking about the best approach...",
            message_index=1,
            model_name="gpt-4o",
        )

    # Add tool call using async API
    async def add_tool_result():
        with ToolResultsStorage(test_project, dialog_id) as storage:
            await storage.store_result(
                tool_call_id="call_456",
                tool_name="write_file",
                args={"path": "output.txt", "content": "result"},
                result={"success": True},
            )

    asyncio.run(add_tool_result())

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["dialog_id"] == dialog_id
    assert data["total_messages"] == 3  # 2 regular + 1 reasoning
    assert data["total_reasoning"] == 1
    assert data["total_tool_calls"] == 1

    # Verify all components are present
    assert len(data["messages"]) == 3  # Includes reasoning inline
    reasoning_msgs = [m for m in data["messages"] if m["type"] == "reasoning"]
    assert len(reasoning_msgs) == 1
    assert len(data["tool_calls"]) == 1


def test_get_history_with_long_result_preview(client, test_project):
    """Test that long tool results are truncated in preview."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)

    # Add tool call with long result using async API
    long_content = "x" * 1000

    async def add_tool_result():
        with ToolResultsStorage(test_project, dialog_id) as storage:
            await storage.store_result(
                tool_call_id="call_789",
                tool_name="test_tool",
                args={},
                result={"data": long_content},
            )

    asyncio.run(add_tool_result())

    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    tool_call = data["tool_calls"][0]

    # Preview should exist (may be "No preview available" if no summary was generated)
    assert "result_preview" in tool_call
    # If there's actual content, it should be truncated to reasonable length
    assert len(tool_call["result_preview"]) <= 250  # Reasonable limit


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
    assert len(data["tool_calls"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
