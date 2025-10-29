"""Test that SSE error events are delivered when LLM streaming fails."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentsmithy.core.project import Project


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


async def failing_response_stream():
    """Mock async iterator that raises an exception (e.g., context window overflow)."""
    # Yield a few chunks first to simulate partial success
    yield {"type": "chat", "content": "Starting response..."}
    yield {"type": "chat", "content": "Processing..."}
    # Then raise an exception like LLM API would
    raise Exception(
        "Your input exceeds the context window of this model. Please adjust your input and try again."
    )


@pytest.mark.asyncio
async def test_error_event_delivered_on_llm_streaming_failure(temp_project):
    """Test that error events are delivered when LLM streaming fails."""
    # Import here to avoid circular import issues
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    # Create ChatService
    service = ChatService()

    # Mock the orchestrator to return a failing stream
    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    # Create async iterator that yields state with failing response
    async def mock_states():
        yield {
            "response": failing_response_stream(),
        }

    mock_graph_execution.__aiter__ = lambda self: mock_states()

    mock_orchestrator.process_request = AsyncMock(
        return_value={"graph_execution": mock_graph_execution}
    )

    # Inject mocked orchestrator
    service._orchestrator = mock_orchestrator

    # Mock vector store sync to avoid RAG calls
    temp_project.get_vector_store = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_store.sync_files_if_needed = AsyncMock(
        return_value={"checked": 0, "reindexed": 0, "removed": 0}
    )
    temp_project.get_vector_store.return_value = mock_vector_store

    # Collect SSE events from stream
    events = []
    error_found = False
    done_found = False

    try:
        async for sse_event in service.stream_chat(
            query="Test query",
            context={},
            dialog_id=dialog_id,
            project_dialog=(temp_project, dialog_id),
        ):
            events.append(sse_event)

            # Parse event data
            import json

            event_data = json.loads(sse_event.get("data", "{}"))

            if event_data.get("type") == "error":
                error_found = True
                assert "context window" in event_data.get("error", "").lower()

            if event_data.get("type") == "done" or event_data.get("done"):
                done_found = True
    except Exception:
        # Stream may raise after emitting events; swallow exception to verify that
        # error/done events were properly delivered before the failure occurred.
        # Intentionally ignore to assert on collected SSE events below.
        pass

    # Verify error and done events were delivered
    assert error_found, f"Error event not found in SSE stream. Events: {events}"
    assert done_found, f"Done event not found in SSE stream. Events: {events}"

    # Verify we got some chat events before the error
    chat_events = [
        e for e in events if "chat" in json.loads(e.get("data", "{}")).get("type", "")
    ]
    assert len(chat_events) > 0, "Should have received chat events before error"


@pytest.mark.asyncio
async def test_error_event_on_immediate_failure(temp_project):
    """Test error delivery when stream fails immediately without any chunks."""
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    async def immediate_fail_stream():
        """Mock stream that fails immediately."""
        raise Exception("API authentication failed")
        yield  # Never reached

    service = ChatService()

    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    async def mock_states():
        yield {
            "response": immediate_fail_stream(),
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

    events = []
    error_found = False

    try:
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
    except Exception:
        # Stream may raise after emitting error event; swallow exception to verify
        # that the error event was properly delivered before the failure occurred.
        # Intentionally ignored in test to continue assertions.
        pass

    assert (
        error_found
    ), f"Error event not delivered on immediate failure. Events: {events}"


@pytest.mark.asyncio
async def test_multiple_response_sources_error_handling(temp_project):
    """Test that errors from agent responses are also caught and delivered."""
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    async def failing_agent_stream():
        yield {"type": "chat", "content": "Agent working..."}
        raise Exception("Agent processing failed")

    service = ChatService()

    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    async def mock_states():
        # State with agent response that fails
        yield {
            "some_agent": {
                "response": failing_agent_stream(),
            }
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

    events = []
    error_found = False

    try:
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
                assert "Agent processing failed" in event_data.get("error", "")
    except Exception:
        # Stream may raise after emitting error event; swallow exception to verify
        # that the error event was properly delivered before the failure occurred.
        pass

    assert error_found, "Error from agent response not delivered"
