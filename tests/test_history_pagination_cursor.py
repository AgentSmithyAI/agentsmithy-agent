"""Test that pagination cursor (before) refers to event position, not message_index."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

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


def test_before_cursor_uses_event_position_not_message_index(client, test_project):
    """Test that 'before' parameter uses position in final events array, not message_index.

    This reproduces the bug where cursor pagination was using message_index instead of
    the actual position in the final events array after merging reasoning/tool_calls.
    """
    # Create dialog with specific structure
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Message 0: user
    history.add_user_message("task 1")

    # Message 1: AI with tool_call
    ai_msg1 = AIMessage(
        content="doing task 1",
        tool_calls=[{"id": "call_1", "name": "tool1", "args": {}}],
    )
    history.add_message(ai_msg1)

    # Add reasoning for message 1
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="thinking about task 1", message_index=1)

    # Message 2: user
    history.add_user_message("task 2")

    # Message 3: AI
    history.add_ai_message("doing task 2")

    # Expected final events array:
    # [0] user: "task 1"
    # [1] reasoning: "thinking about task 1"  (for msg 1)
    # [2] chat: "doing task 1"  (msg 1)
    # [3] tool_call: tool1  (from msg 1)
    # [4] user: "task 2"  (msg 2)
    # [5] chat: "doing task 2"  (msg 3)

    # Get full history to verify structure
    full = client.get(f"/api/dialogs/{dialog_id}/history?limit=100")
    assert full.status_code == 200
    full_events = full.json()["events"]

    # Verify expected structure
    assert len(full_events) == 6
    assert full_events[0]["type"] == "user"
    assert full_events[1]["type"] == "reasoning"
    assert full_events[2]["type"] == "chat"
    assert full_events[3]["type"] == "tool_call"
    assert full_events[4]["type"] == "user"
    assert full_events[5]["type"] == "chat"

    # Now test pagination with before=4
    # Should return events [0,1,2,3] (before position 4 in events array)
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10&before=4")
    assert response.status_code == 200

    data = response.json()
    events = data["events"]

    # Should get events at positions [0,1,2,3]
    assert len(events) == 4
    assert events[0]["type"] == "user"
    assert events[1]["type"] == "reasoning"
    assert events[2]["type"] == "chat"
    assert events[3]["type"] == "tool_call"

    # NOT event[4] (user: "task 2") - that's after cursor


def test_cursor_pagination_with_multiple_reasoning_blocks(client, test_project):
    """Test cursor pagination when messages have multiple reasoning blocks."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Create structure:
    # msg[0]: user
    # msg[1]: AI with 2 reasoning blocks before it

    history.add_user_message("complex task")

    # Add 2 reasoning blocks for same message
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="first thought", message_index=1)
        storage.save(content="second thought", message_index=1)

    history.add_ai_message("i'll do it")

    # Expected events:
    # [0] user
    # [1] reasoning: "first thought"
    # [2] reasoning: "second thought"
    # [3] chat: "i'll do it"

    # Get with before=3 should return [0,1,2]
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10&before=3")
    assert response.status_code == 200

    events = response.json()["events"]
    assert len(events) == 3
    assert events[0]["type"] == "user"
    assert events[1]["type"] == "reasoning"
    assert events[2]["type"] == "reasoning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
