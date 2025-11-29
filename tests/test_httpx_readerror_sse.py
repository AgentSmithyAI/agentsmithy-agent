"""Test that httpx.ReadError during LLM streaming properly delivers error to SSE.

This test reproduces the exact issue reported in logs where httpx.ReadError
occurs during LLM streaming but the error event is not delivered to the SSE client.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agentsmithy.core.project import Project
from agentsmithy.domain.events import ChatEvent, ErrorEvent


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


async def llm_stream_with_httpx_readerror():
    """Mock LLM stream that raises httpx.ReadError mid-stream (simulating network error)."""
    from langchain_core.messages import AIMessageChunk

    # Yield some chunks successfully
    yield AIMessageChunk(content="Starting to ")
    yield AIMessageChunk(content="process your ")

    # Then raise httpx.ReadError like in the real logs
    raise httpx.ReadError("Connection closed by peer")


@pytest.mark.asyncio
async def test_httpx_readerror_delivers_error_to_sse(temp_project):
    """Test that httpx.ReadError during LLM streaming delivers error event to SSE.

    This reproduces the exact bug from logs where httpx.ReadError occurs but
    the error event is not delivered to the client.
    """
    from agentsmithy.services.chat_service import ChatService

    dialog_id = temp_project.create_dialog(title="Test Dialog", set_current=True)

    # Create ChatService and mock the universal agent
    service = ChatService()

    # Create a mock orchestrator that returns a failing stream
    mock_orchestrator = MagicMock()
    mock_graph_execution = MagicMock()

    async def mock_process_with_tools(messages, stream=True):
        """Mock tool executor that yields chunks then raises httpx.ReadError."""
        # This simulates tool_executor._process_streaming behavior
        try:
            async for chunk in llm_stream_with_httpx_readerror():
                # Simulate tool_executor yielding chat chunks (now typed events)
                yield ChatEvent(content=chunk.content)
        except httpx.ReadError as e:
            # This is the exact path in tool_executor.py lines 706-723
            # It should yield ERROR event before returning
            yield ErrorEvent(error=f"LLM error: {str(e)}")
            return

    # Mock the response stream
    async def mock_states():
        yield {
            "response": mock_process_with_tools([], stream=True),
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
    chat_events_count = 0

    try:
        async for sse_event in service.stream_chat(
            query="Test query that will fail with httpx.ReadError",
            context={},
            dialog_id=dialog_id,
            project_dialog=(temp_project, dialog_id),
        ):
            events.append(sse_event)

            # Parse event data
            import json

            event_data = json.loads(sse_event.get("data", "{}"))
            event_type = event_data.get("type", "")

            if event_type == "chat":
                chat_events_count += 1

            if event_type == "error":
                error_found = True
                error_msg = event_data.get("error", "")
                # Verify the error message contains info about httpx.ReadError
                assert (
                    "httpx.ReadError" in error_msg or "LLM error" in error_msg
                ), f"Expected error about httpx.ReadError, got: {error_msg}"

            if event_type == "done" or event_data.get("done"):
                done_found = True
    except Exception as e:
        # Stream should NOT raise - all errors should be delivered via SSE
        pytest.fail(f"Stream raised exception instead of delivering error via SSE: {e}")

    # Debug output if test fails
    if not error_found or not done_found:
        import json

        print("\n=== ALL SSE EVENTS ===")
        for i, event in enumerate(events):
            event_data = json.loads(event.get("data", "{}"))
            print(f"{i}: {event_data.get('type')} - {event_data}")

    # Verify error and done events were delivered
    assert error_found, (
        f"ERROR event not found in SSE stream! This is the bug we're fixing. "
        f"Total events: {len(events)}, Chat events: {chat_events_count}"
    )
    assert done_found, f"DONE event not found in SSE stream. Events: {len(events)}"

    # Verify we got chat events before the error (stream was working before failure)
    assert (
        chat_events_count >= 2
    ), f"Should have received chat events before httpx.ReadError. Got: {chat_events_count}"


@pytest.mark.asyncio
async def test_httpx_readerror_in_tool_executor_direct():
    """Test tool_executor behavior when httpx.ReadError occurs.

    This tests the tool_executor._process_streaming method directly to ensure
    it properly yields ERROR event when httpx.ReadError occurs.
    """
    from langchain_core.messages import HumanMessage

    from agentsmithy.llm.provider import LLMProvider
    from agentsmithy.tools.registry import ToolRegistry
    from agentsmithy.tools.tool_executor import ToolExecutor

    # Create minimal tool executor
    tool_manager = ToolRegistry()

    # Mock LLM provider
    mock_llm_provider = MagicMock(spec=LLMProvider)
    mock_llm = MagicMock()

    # Mock bind_tools to return mock LLM
    mock_llm_provider.bind_tools = MagicMock(return_value=mock_llm)

    # Mock astream to return stream that raises httpx.ReadError
    mock_llm.astream = MagicMock(return_value=llm_stream_with_httpx_readerror())
    mock_llm_provider.get_stream_kwargs = MagicMock(return_value={})

    tool_executor = ToolExecutor(tool_manager, mock_llm_provider)

    # Process messages and collect events
    messages = [HumanMessage(content="Test query")]
    events = []
    error_found = False

    try:
        async for event in tool_executor.process_with_tools(messages, stream=True):
            events.append(event)
            if isinstance(event, ErrorEvent):
                error_found = True
                # Verify error message
                assert (
                    "LLM error:" in event.error
                ), f"Expected 'LLM error:' in message, got: {event.error}"
    except Exception as e:
        # Tool executor should NOT raise - it should yield ERROR and return
        pytest.fail(f"Tool executor raised exception instead of yielding ERROR: {e}")

    # Debug output
    if not error_found:
        print("\n=== TOOL EXECUTOR EVENTS ===")
        for i, event in enumerate(events):
            print(f"{i}: {event}")

    # Verify ERROR event was yielded
    assert error_found, (
        f"Tool executor did not yield ERROR event when httpx.ReadError occurred! "
        f"Total events: {len(events)}"
    )

    # Verify we got some chat events before the error
    chat_events = [e for e in events if isinstance(e, ChatEvent)]
    assert len(chat_events) >= 1, "Should have received chat events before error"
