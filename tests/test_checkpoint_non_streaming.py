"""Test that checkpoint and session are included in non-streaming responses."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentsmithy.core.project import Project
from agentsmithy.services.chat_service import ChatService


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


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator that returns a simple response."""
    orchestrator = MagicMock()
    orchestrator.process_request = AsyncMock(
        return_value={
            "response": "Test response",
            "metadata": {"some_key": "some_value"},
        }
    )
    return orchestrator


@pytest.mark.asyncio
async def test_non_streaming_includes_checkpoint_in_metadata(
    temp_project, mock_orchestrator
):
    """Test that non-streaming chat includes checkpoint and session in metadata."""
    service = ChatService()
    service._orchestrator = mock_orchestrator

    dialog_id = temp_project.create_dialog(title="Test Dialog")

    # Call non-streaming chat endpoint
    result = await service.chat(
        query="Test query",
        context={},
        dialog_id=dialog_id,
        project=temp_project,
    )

    # Verify result structure
    assert "response" in result
    assert "metadata" in result

    # Verify checkpoint and session are in metadata
    assert "checkpoint" in result["metadata"]
    assert "session" in result["metadata"]

    # Verify checkpoint ID format (should be a git commit hash)
    checkpoint_id = result["metadata"]["checkpoint"]
    assert isinstance(checkpoint_id, str)
    assert len(checkpoint_id) == 40  # Git SHA-1 is 40 chars

    # Verify session format
    session_id = result["metadata"]["session"]
    assert isinstance(session_id, str)
    assert session_id.startswith("session_")

    # Verify other metadata is preserved
    assert result["metadata"]["some_key"] == "some_value"


@pytest.mark.asyncio
async def test_non_streaming_checkpoint_matches_history(
    temp_project, mock_orchestrator
):
    """Test that checkpoint in metadata matches the one stored in history."""
    service = ChatService()
    service._orchestrator = mock_orchestrator

    dialog_id = temp_project.create_dialog(title="Test Dialog")

    # Call non-streaming chat endpoint
    result = await service.chat(
        query="Test query",
        context={},
        dialog_id=dialog_id,
        project=temp_project,
    )

    # Get the user message from history
    history = temp_project.get_dialog_history(dialog_id)
    messages = history.get_messages()
    user_messages = [m for m in messages if m.type == "human"]

    assert len(user_messages) > 0
    user_msg = user_messages[-1]

    # Checkpoint in metadata should match the one in history
    checkpoint_in_metadata = result["metadata"]["checkpoint"]
    checkpoint_in_history = getattr(user_msg, "additional_kwargs", {}).get("checkpoint")

    assert checkpoint_in_metadata == checkpoint_in_history

    # Session should also match
    session_in_metadata = result["metadata"]["session"]
    session_in_history = getattr(user_msg, "additional_kwargs", {}).get("session")

    assert session_in_metadata == session_in_history
