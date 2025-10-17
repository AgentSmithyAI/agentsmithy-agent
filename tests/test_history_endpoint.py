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
    assert data["total_events"] == 2  # Total number of messages
    assert data["has_more"] is False
    assert data["first_idx"] == 0
    assert data["last_idx"] == 1

    # Check events - only messages have idx
    events = data["events"]
    assert len(events) == 2
    assert events[0]["type"] == "user"
    assert events[0]["content"] == "Hello"
    assert events[0]["idx"] == 0

    assert events[1]["type"] == "chat"
    assert events[1]["content"] == "Hi there!"
    assert events[1]["idx"] == 1


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

    # Check that reasoning is in events (but without idx)
    events = data["events"]
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1

    reasoning = reasoning_events[0]
    assert reasoning["content"] == "First, I need to understand the context..."
    assert reasoning["model_name"] == "gpt-4o"
    assert reasoning.get("idx") is None  # Reasoning doesn't have idx


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

    # Check tool call event (without idx)
    events = data["events"]
    tool_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "read_file"
    assert tool_events[0]["args"] == {"path": "file.txt"}
    assert tool_events[0].get("idx") is None  # Tool calls don't have idx


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
    assert data["total_events"] == 2  # 2 messages (user + ai)

    # Verify all event types are present
    events = data["events"]
    assert sum(1 for e in events if e["type"] == "reasoning") == 1
    assert sum(1 for e in events if e["type"] == "tool_call") == 1
    assert sum(1 for e in events if e["type"] == "chat") >= 1
    assert sum(1 for e in events if e["type"] == "user") >= 1
    
    # Only messages should have idx
    for event in events:
        if event["type"] in ["user", "chat"]:
            assert event.get("idx") is not None
        else:
            assert event.get("idx") is None


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
    assert data["total_events"] == 0
    assert data["has_more"] is False


def test_get_history_pagination_default(client, test_project):
    """Test default pagination - returns last 20 messages."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add 30 messages (15 pairs of user/AI)
    for i in range(15):
        history.add_user_message(f"User message {i}")
        history.add_ai_message(f"AI response {i}")

    # Get history without pagination params (should return last 20 messages)
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert data["total_events"] == 30  # Total messages
    assert data["has_more"] is True  # There are 10 more messages before
    assert data["first_idx"] == 10  # Starting from message index 10
    assert data["last_idx"] == 29  # Ending at message index 29

    # Check that we got events for the last 20 messages
    events = data["events"]
    message_events = [e for e in events if e["type"] in ["user", "chat"]]
    assert len(message_events) == 20
    assert message_events[0]["idx"] == 10
    assert message_events[-1]["idx"] == 29


def test_get_history_pagination_custom_limit(client, test_project):
    """Test custom limit."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add 50 messages
    for i in range(50):
        history.add_user_message(f"Message {i}")

    # Get last 10 messages
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10")
    assert response.status_code == 200

    data = response.json()
    assert data["total_events"] == 50
    assert data["has_more"] is True
    assert data["first_idx"] == 40  # First message index
    assert data["last_idx"] == 49  # Last message index
    
    events = data["events"]
    message_events = [e for e in events if e["type"] == "user"]
    assert len(message_events) == 10


def test_get_history_pagination_with_before_cursor(client, test_project):
    """Test cursor-based pagination with before (scrolling up)."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add 50 messages
    for i in range(50):
        history.add_user_message(f"Message {i}")

    # First request: get last 20 messages (indices 30-49)
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=20")
    data = response.json()
    assert data["first_idx"] == 30
    assert data["last_idx"] == 49

    # Second request: get 20 messages before cursor (indices 10-29)
    cursor = data["first_idx"]
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=20&before={cursor}")
    assert response.status_code == 200

    data = response.json()
    assert data["total_events"] == 50
    assert data["has_more"] is True
    assert data["first_idx"] == 10
    assert data["last_idx"] == 29
    
    events = data["events"]
    message_events = [e for e in events if e["type"] == "user"]
    assert len(message_events) == 20

    # Third request: get remaining messages (indices 0-9)
    cursor = data["first_idx"]
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=20&before={cursor}")
    assert response.status_code == 200

    data = response.json()
    assert data["total_events"] == 50
    assert data["has_more"] is False  # No more messages before
    assert data["first_idx"] == 0
    assert data["last_idx"] == 9
    
    events = data["events"]
    message_events = [e for e in events if e["type"] == "user"]
    assert len(message_events) == 10  # Only 10 messages left


def test_get_history_pagination_chronological_order(client, test_project):
    """Test that paginated messages are always in chronological order."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)

    # Add 30 messages
    for i in range(30):
        history.add_user_message(f"Message {i}")

    # Get last 10 messages
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=10")
    data = response.json()
    events = data["events"]

    # Check chronological order of messages
    message_events = [e for e in events if e.get("idx") is not None]
    for i in range(len(message_events) - 1):
        assert message_events[i]["idx"] < message_events[i + 1]["idx"]

    # Get previous 10 messages
    response = client.get(
        f"/api/dialogs/{dialog_id}/history?limit=10&before={data['first_idx']}"
    )
    data = response.json()
    events = data["events"]

    # Check chronological order again
    message_events = [e for e in events if e.get("idx") is not None]
    for i in range(len(message_events) - 1):
        assert message_events[i]["idx"] < message_events[i + 1]["idx"]


def test_get_history_sequential_indices(client, test_project):
    """Test that idx values are sequential without gaps, even when DB has ToolMessages."""
    from langchain_core.messages import AIMessage, ToolMessage
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add messages with ToolMessages in between
    history.add_user_message("Message 0")  # idx=0
    history.add_ai_message("Message 1")     # idx=1
    
    # Add ToolMessage (should be filtered out)
    tool_msg = ToolMessage(content="tool result", tool_call_id="call_1")
    history.add_message(tool_msg)           # DB idx=2, but NOT visible
    
    history.add_user_message("Message 2")  # idx=2 (sequential!)
    
    # Add empty AI message (should be filtered out)
    empty_ai = AIMessage(
        content="",
        tool_calls=[{"id": "call_2", "name": "test", "args": {}}]
    )
    history.add_message(empty_ai)           # DB idx=4, but NOT visible
    
    history.add_ai_message("Message 3")     # idx=3 (sequential!)
    
    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200
    
    data = response.json()
    # total_events counts only non-empty messages (those with idx)
    assert data["total_events"] == 4  # 4 non-empty messages
    
    # Check that idx values are sequential 0,1,2,3 (empty AI doesn't get idx)
    events = data["events"]
    message_events = [e for e in events if e.get("idx") is not None]
    assert len(message_events) == 4  # Only non-empty messages have idx
    
    indices = [e["idx"] for e in message_events]
    assert indices == [0, 1, 2, 3], f"Expected sequential [0,1,2,3], got {indices}"
    
    # Verify tool_call from empty AI is present (without idx)
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "test"
    
    # Test pagination with before
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=2&before=2")
    data = response.json()
    
    message_events = [e for e in data["events"] if e.get("idx") is not None]
    indices = [e["idx"] for e in message_events]
    assert indices == [0, 1], f"Expected [0,1] before idx=2, got {indices}"
    assert data["first_idx"] == 0
    assert data["last_idx"] == 1


def test_get_history_with_orphan_reasoning(client, test_project):
    """Test that orphan reasoning (message_index=-1) appears at the end."""
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add messages
    history.add_user_message("Question")
    history.add_ai_message("Answer")
    
    # Add orphan reasoning (message_index=-1, created after messages)
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Thinking about next step...",
            message_index=-1,
            model_name="gpt-4o",
        )
    
    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200
    
    data = response.json()
    events = data["events"]
    
    # Orphan reasoning should be at the end
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1
    
    # It should appear after all messages
    last_msg_idx = max(e.get("idx", -1) for e in events)
    reasoning_position = events.index(reasoning_events[0])
    message_positions = [i for i, e in enumerate(events) if e.get("idx") is not None]
    if message_positions:
        assert reasoning_position > max(message_positions), "Orphan reasoning should be after messages"


def test_get_history_orphan_reasoning_shows_all(client, test_project):
    """Test that orphan reasoning (message_index=-1) always shows on last page.
    
    Note: We don't filter by timestamp since message_store and dialog_reasoning
    are separate tables. Old orphans should be manually cleaned up or linked.
    """
    import time
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add old orphan reasoning BEFORE messages
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Old orphan reasoning",
            message_index=-1,
            model_name="gpt-4o",
        )
    
    # Small delay to ensure timestamp difference
    time.sleep(0.01)
    
    # Add messages AFTER the orphan reasoning
    history.add_user_message("Question")
    history.add_ai_message("Answer")
    
    # Get history - orphan WILL appear (we don't filter by timestamp)
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200
    
    data = response.json()
    events = data["events"]
    
    # Orphan reasoning appears (old or new, doesn't matter)
    message_events = [e for e in events if e.get("idx") is not None]
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    
    assert len(message_events) == 2
    assert len(reasoning_events) == 1  # Orphan is shown


def test_get_history_orphan_reasoning_recent_only(client, test_project):
    """Test that only recent orphan reasoning (after last message) is shown."""
    import time
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add messages
    history.add_user_message("Question 1")
    history.add_ai_message("Answer 1")
    
    time.sleep(0.01)
    
    # Add new orphan reasoning AFTER messages
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Fresh thinking...",
            message_index=-1,
            model_name="gpt-4o",
        )
    
    # Get history - new orphan SHOULD appear
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200
    
    data = response.json()
    events = data["events"]
    
    reasoning_events = [e for e in events if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1
    assert reasoning_events[0]["content"] == "Fresh thinking..."


def test_get_history_orphan_only_in_last_page(client, test_project):
    """Test that orphan reasoning only appears when loading the last page."""
    import time
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add 10 messages
    for i in range(10):
        history.add_user_message(f"Message {i}")
    
    time.sleep(0.01)
    
    # Add orphan reasoning after all messages
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Current thinking...",
            message_index=-1,
            model_name="gpt-4o",
        )
    
    # Get first 5 messages - orphan should NOT appear
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=5&before=5")
    data = response.json()
    reasoning_events = [e for e in data["events"] if e["type"] == "reasoning"]
    assert len(reasoning_events) == 0, "Orphan should not appear in earlier pages"
    
    # Get last 5 messages - orphan SHOULD appear
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=5")
    data = response.json()
    reasoning_events = [e for e in data["events"] if e["type"] == "reasoning"]
    assert len(reasoning_events) == 1
    assert reasoning_events[0]["content"] == "Current thinking..."


def test_get_history_events_ordering(client, test_project):
    """Test that events appear in correct order: reasoning -> message -> tool_calls -> file_edits."""
    from langchain_core.messages import AIMessage
    from agentsmithy_server.dialogs.storages.file_edits import DialogFileEditStorage
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Add user message
    history.add_user_message("Do task")
    
    # Add AI message with tool calls
    ai_msg = AIMessage(
        content="I'll do it",
        tool_calls=[
            {"id": "call_1", "name": "write_file", "args": {"path": "a.txt"}},
            {"id": "call_2", "name": "write_file", "args": {"path": "b.txt"}},
        ],
    )
    history.add_message(ai_msg)
    
    # Add reasoning for AI message (index 1)
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(
            content="Reasoning block 1",
            message_index=1,
            model_name="gpt-4o",
        )
        storage.save(
            content="Reasoning block 2",
            message_index=1,
            model_name="gpt-4o",
        )
    
    # Add file edits for AI message
    with DialogFileEditStorage(test_project, dialog_id) as storage:
        storage.save(file="a.txt", message_index=1)
        storage.save(file="b.txt", message_index=1)
    
    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    assert response.status_code == 200
    
    data = response.json()
    events = data["events"]
    
    # Find AI message position
    ai_msg_pos = next(i for i, e in enumerate(events) if e.get("idx") == 1)
    
    # Check order: reasoning blocks should come BEFORE message
    reasoning_positions = [i for i, e in enumerate(events) if e["type"] == "reasoning"]
    assert len(reasoning_positions) == 2
    for pos in reasoning_positions:
        assert pos < ai_msg_pos, "Reasoning should come before message"
    
    # Tool calls should come AFTER message
    tool_call_positions = [i for i, e in enumerate(events) if e["type"] == "tool_call"]
    assert len(tool_call_positions) == 2
    for pos in tool_call_positions:
        assert pos > ai_msg_pos, "Tool calls should come after message"
    
    # File edits should come AFTER tool calls
    file_edit_positions = [i for i, e in enumerate(events) if e["type"] == "file_edit"]
    assert len(file_edit_positions) == 2
    for pos in file_edit_positions:
        assert pos > ai_msg_pos, "File edits should come after message"
        assert pos > max(tool_call_positions), "File edits should come after tool calls"


def test_get_history_multiple_messages_ordering(client, test_project):
    """Test that events from different messages don't intermix."""
    from langchain_core.messages import AIMessage
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Message 0
    history.add_user_message("Task 1")
    
    # Message 1 with reasoning
    history.add_ai_message("Response 1")
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="Thinking 1", message_index=1, model_name="gpt-4o")
    
    # Message 2  
    history.add_user_message("Task 2")
    
    # Message 3 with reasoning and tool call
    ai_msg = AIMessage(
        content="Response 2",
        tool_calls=[{"id": "call_1", "name": "test", "args": {}}],
    )
    history.add_message(ai_msg)
    with DialogReasoningStorage(test_project, dialog_id) as storage:
        storage.save(content="Thinking 2", message_index=3, model_name="gpt-4o")
    
    # Get history
    response = client.get(f"/api/dialogs/{dialog_id}/history")
    data = response.json()
    events = data["events"]
    
    # Extract event types with their indices
    event_sequence = [(e.get("idx"), e["type"]) for e in events]
    
    # Check that all events for idx=1 come before events for idx=2
    msg1_events = [i for i, (idx, _) in enumerate(event_sequence) if idx == 1]
    msg2_events = [i for i, (idx, _) in enumerate(event_sequence) if idx == 2]
    msg3_events = [i for i, (idx, _) in enumerate(event_sequence) if idx == 3]
    
    # Events for message 1 should come before message 2
    assert max(msg1_events) < min(msg2_events), "Message 1 events should come before Message 2"
    
    # Events for message 2 should come before message 3
    assert max(msg2_events) < min(msg3_events), "Message 2 events should come before Message 3"


def test_get_history_with_many_empty_ai_messages(client, test_project):
    """Test pagination when there are many empty AI messages with tool_calls.
    
    Reproduces the issue where limit=4 should return 4 non-empty messages,
    but actually returns only 1 because start_pos calculation is wrong.
    """
    from langchain_core.messages import AIMessage, ToolMessage
    
    dialog_id = test_project.create_dialog(title="test", set_current=True)
    history = test_project.get_dialog_history(dialog_id)
    
    # Simulate real scenario: user asks, agent responds, then does 5 tool calls
    history.add_user_message("Question 1")  # idx=0
    history.add_ai_message("Answer 1")       # idx=1
    
    # 5 empty AI messages with tool_calls (like in real dialog)
    for i in range(5):
        empty_ai = AIMessage(
            content="",
            tool_calls=[{"id": f"call_{i}", "name": "read_file", "args": {"path": f"file{i}.txt"}}]
        )
        history.add_message(empty_ai)
        # Add ToolMessage result
        tool_result = ToolMessage(content=f"result {i}", tool_call_id=f"call_{i}")
        history.add_message(tool_result)
    
    history.add_user_message("Question 2")  # idx=2
    history.add_ai_message("Answer 2")       # idx=3
    
    # Total: 4 non-empty (2 user + 2 ai) + 5 empty AI + 5 ToolMessage
    # Visible (non-ToolMessage): 4 non-empty + 5 empty = 9
    
    # Request last 4 messages - should get 4 NON-EMPTY messages with idx
    response = client.get(f"/api/dialogs/{dialog_id}/history?limit=4")
    data = response.json()
    
    # Should have exactly 4 messages with idx (the 4 non-empty ones)
    message_events = [e for e in data["events"] if e.get("idx") is not None]
    assert len(message_events) == 4, f"Expected 4 messages with idx, got {len(message_events)}"
    
    indices = [e["idx"] for e in message_events]
    assert indices == [0, 1, 2, 3], f"Expected [0,1,2,3], got {indices}"
    
    # But should also have 5 tool_calls from empty AI messages
    tool_calls = [e for e in data["events"] if e["type"] == "tool_call"]
    assert len(tool_calls) == 5, f"Expected 5 tool_calls, got {len(tool_calls)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

