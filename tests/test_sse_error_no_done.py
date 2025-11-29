"""Test that ERROR events are followed by DONE event in SSE stream.

This reproduces the bug where ERROR event is logged but done event is not sent,
leaving the client hanging without a proper stream termination.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentsmithy.core.project import Project
from agentsmithy.domain.events import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    ReasoningEndEvent,
    ReasoningEvent,
    ReasoningStartEvent,
)


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


async def failing_stream_after_reasoning():
    """Mock stream that yields reasoning, then error (simulating real scenario from logs)."""
    # Yield reasoning events (now typed)
    yield ReasoningStartEvent()
    yield ReasoningEvent(content="Let me think...")
    yield ReasoningEvent(content=" about this problem...")
    yield ReasoningEndEvent()

    # Then yield error event (like tool_executor does)
    yield ErrorEvent(error="LLM error: ")

    # Yield DONE event (tool_executor now yields this after ERROR)
    yield DoneEvent()


@pytest.mark.asyncio
async def test_error_event_followed_by_done(temp_project):
    """Test that ERROR event is always followed by DONE event in SSE stream.

    This reproduces the bug from logs where ERROR event is logged but
    the stream doesn't complete with DONE event, leaving client hanging.
    """
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    service = ChatService()

    # Create a mock orchestrator
    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    async def mock_states():
        yield {
            "response": failing_stream_after_reasoning(),
        }

    mock_graph_execution.__aiter__ = lambda self: mock_states()
    mock_orchestrator.process_request = AsyncMock(
        return_value={"graph_execution": mock_graph_execution}
    )

    service._orchestrator = mock_orchestrator

    # Mock vector store
    temp_project.get_vector_store = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_store.sync_files_if_needed = AsyncMock(
        return_value={"checked": 0, "reindexed": 0, "removed": 0}
    )
    temp_project.get_vector_store.return_value = mock_vector_store

    # Collect SSE events with timeout protection
    events = []
    error_found = False
    done_found = False
    reasoning_events_count = 0

    try:
        # Add timeout to detect hanging streams
        async def collect_events():
            nonlocal error_found, done_found, reasoning_events_count
            async for sse_event in service.stream_chat(
                query="Test query",
                context={},
                dialog_id=dialog_id,
                project_dialog=(temp_project, dialog_id),
            ):
                events.append(sse_event)

                import json

                event_data = json.loads(sse_event.get("data", "{}"))
                event_type = event_data.get("type", "")

                if event_type in ("reasoning", "reasoning_start", "reasoning_end"):
                    reasoning_events_count += 1

                if event_type == "error":
                    error_found = True
                    error_msg = event_data.get("error", "")
                    print(f"ERROR event: {error_msg}")

                if event_type == "done" or event_data.get("done"):
                    done_found = True
                    print("DONE event received")
                    break

        # Run with timeout to detect if stream hangs
        await asyncio.wait_for(collect_events(), timeout=3.0)

    except TimeoutError:
        pytest.fail(
            f"Stream TIMED OUT! This is the bug - stream hangs after ERROR event. "
            f"Events received: {len(events)}, Error found: {error_found}, Done found: {done_found}"
        )
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")

    # Debug output
    if not done_found:
        import json

        print("\n=== ALL SSE EVENTS ===")
        for i, event in enumerate(events):
            event_data = json.loads(event.get("data", "{}"))
            print(f"{i}: {event_data.get('type')} - {event_data}")

    # Main assertion: DONE must follow ERROR
    assert error_found, "ERROR event not found in stream"
    assert done_found, (
        f"DONE event NOT FOUND after ERROR! This is the bug. "
        f"Stream had {len(events)} events, {reasoning_events_count} reasoning events, "
        f"but no DONE event after ERROR. Client is left hanging!"
    )


@pytest.mark.asyncio
async def test_error_with_empty_message_followed_by_done(temp_project):
    """Test ERROR event with empty message is still followed by DONE.

    In the real logs, error message was 'LLM error: ' (almost empty).
    This could be causing issues with stream termination.
    """
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    service = ChatService()

    async def stream_with_empty_error():
        """Stream that yields error with empty/whitespace message."""
        yield ChatEvent(content="Starting...")
        # Empty error message like in real logs
        yield ErrorEvent(error="")
        # Yield DONE event (tool_executor now yields this after ERROR)
        yield DoneEvent()

    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    async def mock_states():
        yield {"response": stream_with_empty_error()}

    mock_graph_execution.__aiter__ = lambda self: mock_states()
    mock_orchestrator.process_request = AsyncMock(
        return_value={"graph_execution": mock_graph_execution}
    )

    service._orchestrator = mock_orchestrator

    # Mock vector store
    temp_project.get_vector_store = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_store.sync_files_if_needed = AsyncMock(
        return_value={"checked": 0, "reindexed": 0, "removed": 0}
    )
    temp_project.get_vector_store.return_value = mock_vector_store

    events = []
    error_found = False
    done_found = False

    try:

        async def collect_events():
            nonlocal error_found, done_found
            async for sse_event in service.stream_chat(
                query="Test",
                context={},
                dialog_id=dialog_id,
                project_dialog=(temp_project, dialog_id),
            ):
                events.append(sse_event)
                import json

                event_data = json.loads(sse_event.get("data", "{}"))
                if event_data.get("type") == "error":
                    error_found = True
                if event_data.get("type") == "done" or event_data.get("done"):
                    done_found = True
                    break

        await asyncio.wait_for(collect_events(), timeout=2.0)

    except TimeoutError:
        pytest.fail(
            f"Stream TIMED OUT with empty error message! "
            f"Error found: {error_found}, Done found: {done_found}"
        )

    assert error_found, "ERROR event with empty message not found"
    assert done_found, (
        "DONE event NOT FOUND after ERROR with empty message! "
        "Empty error messages should still be followed by DONE."
    )
