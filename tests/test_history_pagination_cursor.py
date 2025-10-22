"""Test that pagination cursor (before) works correctly with new logic."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agentsmithy.api.app import create_app
from agentsmithy.core.project import Project
from agentsmithy.dialogs.storages.reasoning import DialogReasoningStorage


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
        "agentsmithy.core.project.get_current_project",
        mock_get_current_project,
    )
    monkeypatch.setattr(
        "agentsmithy.api.deps.get_current_project",
        mock_get_current_project,
    )

    app = create_app()
    return TestClient(app)


def test_before_cursor_uses_message_index(client, test_project):
    """Test that 'before' parameter uses sequential message indices.

    New logic: before refers to the idx value (sequential index of non-empty messages),
    not position in events array.
    """
    # Create dialog with specific structure
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Message 0: user (idx=0)
    history.add_user_message("task 1")

    # Message 1: AI with tool_call (idx=1)
    ai_msg1 = AIMessage(
        content="doing task 1",
        tool_calls=[{"id": "call_1", "name": "tool1", "args": {}}],
    )
    history.add_message(ai_msg1)

    # Add reasoning for message 1
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="thinking about task 1", message_index=1)

    # Message 2: user (idx=2)
    history.add_user_message("task 2")

    # Message 3: AI (idx=3)
    history.add_ai_message("doing task 2")

    # Get full history to verify structure
    full = client.get(f"/api/dialogs/{dialog_id}/history?limit=100")
    assert full.status_code == 200
    full_events = full.json()["events"]

    # Verify events with idx
    message_events = [e for e in full_events if e.get("idx") is not None]
    assert len(message_events) == 4  # 4 messages with idx
    assert [e["idx"] for e in message_events] == [0, 1, 2, 3]

    # Now test pagination with before=2
    # Should return messages with idx < 2, i.e., idx=[0,1]
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10&before=2")
    assert response.status_code == 200

    data = response.json()
    events = data["events"]

    # Should get messages with idx 0 and 1 (+ their reasoning/tool_calls)
    message_events = [e for e in events if e.get("idx") is not None]
    indices = [e["idx"] for e in message_events]
    assert indices == [0, 1], f"Expected [0,1] before idx=2, got {indices}"

    # Should include reasoning for message 1
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1

    # Should include tool_call for message 1
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1


def test_cursor_pagination_with_multiple_reasoning_blocks(client, test_project):
    """Test cursor pagination when messages have multiple reasoning blocks."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Message 0: user (idx=0)
    history.add_user_message("complex task")

    # Add 2 reasoning blocks for message 1
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="first thought", message_index=1)
        storage.save(content="second thought", message_index=1)

    # Message 1: AI (idx=1)
    history.add_ai_message("i'll do it")

    # Get full history
    full = client.get(f"/api/dialogs/{dialog_id}/history")
    full_events = full.json()["events"]

    # Should have: user(idx=0), reasoning, reasoning, chat(idx=1)
    assert len(full_events) == 4
    message_events = [e for e in full_events if e.get("idx") is not None]
    assert len(message_events) == 2  # 2 messages with idx

    # Get with before=1 should return only message with idx=0 and its events
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10&before=1")
    assert response.status_code == 200

    events = response.json()["events"]

    # Should have only message with idx=0 (no reasoning since reasoning is for idx=1)
    message_events = [e for e in events if e.get("idx") is not None]
    assert len(message_events) == 1
    assert message_events[0]["idx"] == 0
    assert message_events[0]["type"] == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
