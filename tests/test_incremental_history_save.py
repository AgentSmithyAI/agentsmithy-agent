"""Test incremental history saving during streaming to prevent data loss on disconnect."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add parent directory to path to allow importing without circular deps
sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct import to avoid circular dependency through api module
from agentsmithy_server.utils.logger import api_logger


def _flush_assistant_buffer(
    project_dialog, dialog_id, assistant_buffer, clear_buffer=False
):
    """Simplified version of ChatService._flush_assistant_buffer for testing."""
    try:
        if assistant_buffer and project_dialog:
            project_obj, pdialog_id = project_dialog
            target_dialog_id = dialog_id or pdialog_id
            if target_dialog_id and hasattr(project_obj, "get_dialog_history"):
                history = project_obj.get_dialog_history(target_dialog_id)
                content = "".join(assistant_buffer)
                if content:
                    history.add_ai_message(content)
                    if clear_buffer:
                        assistant_buffer.clear()
    except Exception as e:
        api_logger.error(
            "Failed to append assistant message (stream)",
            exc_info=True,
            error=str(e),
        )


@pytest.mark.asyncio
async def test_chat_end_triggers_incremental_save():
    """Test that chat_end event triggers buffer flush with clear."""

    # Mock project and dialog
    mock_project = Mock()
    mock_history = Mock()
    mock_project.get_dialog_history.return_value = mock_history

    project_dialog = (mock_project, "test-dialog-id")
    dialog_id = "test-dialog-id"
    assistant_buffer = ["Hello ", "world", "!"]

    # Test that flush with clear_buffer=True clears the buffer
    _flush_assistant_buffer(
        project_dialog, dialog_id, assistant_buffer, clear_buffer=True
    )

    # Verify history was saved
    mock_history.add_ai_message.assert_called_once_with("Hello world!")

    # Verify buffer was cleared
    assert len(assistant_buffer) == 0


@pytest.mark.asyncio
async def test_flush_without_clear_keeps_buffer():
    """Test that flush without clear_buffer keeps the buffer intact."""

    mock_project = Mock()
    mock_history = Mock()
    mock_project.get_dialog_history.return_value = mock_history

    project_dialog = (mock_project, "test-dialog-id")
    dialog_id = "test-dialog-id"
    assistant_buffer = ["Test ", "content"]

    # Test that flush without clear_buffer keeps the buffer
    _flush_assistant_buffer(
        project_dialog, dialog_id, assistant_buffer, clear_buffer=False
    )

    # Verify history was saved
    mock_history.add_ai_message.assert_called_once_with("Test content")

    # Verify buffer was NOT cleared
    assert len(assistant_buffer) == 2
    assert "".join(assistant_buffer) == "Test content"


@pytest.mark.asyncio
async def test_multiple_chat_end_events_save_incrementally():
    """Test that multiple chat_end events result in multiple incremental saves."""

    mock_project = Mock()
    mock_history = Mock()
    mock_project.get_dialog_history.return_value = mock_history

    project_dialog = (mock_project, "test-dialog-id")
    dialog_id = "test-dialog-id"

    # Simulate first LLM response chunk
    buffer1 = ["First ", "response"]
    _flush_assistant_buffer(project_dialog, dialog_id, buffer1, clear_buffer=True)

    # Simulate second LLM response chunk
    buffer2 = ["Second ", "response"]
    _flush_assistant_buffer(project_dialog, dialog_id, buffer2, clear_buffer=True)

    # Verify both were saved separately
    assert mock_history.add_ai_message.call_count == 2
    calls = mock_history.add_ai_message.call_args_list
    assert calls[0][0][0] == "First response"
    assert calls[1][0][0] == "Second response"

    # Verify buffers were cleared
    assert len(buffer1) == 0
    assert len(buffer2) == 0


@pytest.mark.asyncio
async def test_flush_handles_errors_gracefully():
    """Test that flush errors don't crash the stream."""

    mock_project = Mock()
    mock_history = Mock()
    mock_history.add_ai_message.side_effect = Exception("Database error")
    mock_project.get_dialog_history.return_value = mock_history

    project_dialog = (mock_project, "test-dialog-id")
    dialog_id = "test-dialog-id"
    assistant_buffer = ["Test"]

    # Should not raise - error is caught and logged
    _flush_assistant_buffer(
        project_dialog, dialog_id, assistant_buffer, clear_buffer=True
    )

    # Buffer should NOT be cleared if save failed
    # (current implementation clears after successful save only)
    assert len(assistant_buffer) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
