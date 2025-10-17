"""Test edge cases for history endpoint."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from agentsmithy_server.api.app import create_app
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


def test_empty_ai_after_pagination_limit(client, test_project):
    """Test that empty AI messages after pagination limit still show tool_calls."""

    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add 5 user-ai pairs
    for i in range(5):
        history.add_user_message(f"Question {i}")
        history.add_ai_message(f"Answer {i}")

    # Total: 10 non-empty messages (idx 0-9)

    # Add empty AI with tool_calls AFTER the last message
    empty_ai = AIMessage(
        content="",
        tool_calls=[
            {"id": "call_final", "name": "final_tool", "args": {"test": "data"}}
        ],
    )
    history.add_message(empty_ai)

    # Request last 3 messages (should be messages 7,8,9)
    # But empty AI is at position 10 (after idx=9)
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=3")
    data = response.json()

    # Should have 3 messages with idx
    message_events = [e for e in data["events"] if e.get("idx") is not None]
    assert len(message_events) == 3
    indices = [e["idx"] for e in message_events]
    assert indices == [7, 8, 9]

    # BUG: Should also have tool_call from empty AI at position 10
    # But it's outside the pagination window!
    tool_calls = [e for e in data["events"] if e["type"] == "tool_call"]

    # This SHOULD be 1, but might be 0 if not loaded
    event_types = [e["type"] for e in data["events"]]
    assert (
        len(tool_calls) == 1
    ), f"Expected 1 tool_call, got {len(tool_calls)}. Events: {event_types}"
