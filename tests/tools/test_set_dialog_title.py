"""Tests for set_dialog_title tool."""

from unittest.mock import Mock

import pytest

from agentsmithy_server.tools.builtin.set_dialog_title import SetDialogTitleTool


@pytest.mark.asyncio
async def test_set_dialog_title_success():
    """Test successfully setting dialog title."""
    # Arrange
    mock_project = Mock()
    mock_project.upsert_dialog_meta = Mock()

    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Act
    result = await tool._arun(title="My Test Dialog Title")

    # Assert
    assert result["type"] == "success"
    assert result["tool"] == "set_dialog_title"
    assert result["title"] == "My Test Dialog Title"
    mock_project.upsert_dialog_meta.assert_called_once_with(
        "test_dialog_id", title="My Test Dialog Title"
    )


@pytest.mark.asyncio
async def test_set_dialog_title_no_context():
    """Test setting title without context fails gracefully."""
    # Arrange
    tool = SetDialogTitleTool()
    # Don't set context

    # Act
    result = await tool._arun(title="Title")

    # Assert
    assert result["type"] == "tool_error"
    assert result["code"] == "no_context"
    assert "No dialog context" in result["error"]


@pytest.mark.asyncio
async def test_set_dialog_title_empty_title():
    """Test setting empty title returns error."""
    # Arrange
    mock_project = Mock()
    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Act
    result = await tool._arun(title="")

    # Assert
    assert result["type"] == "tool_error"
    assert result["code"] == "invalid_title"
    assert "cannot be empty" in result["error"]


@pytest.mark.asyncio
async def test_set_dialog_title_whitespace_only():
    """Test setting whitespace-only title returns error."""
    # Arrange
    mock_project = Mock()
    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Act
    result = await tool._arun(title="   ")

    # Assert
    assert result["type"] == "tool_error"
    assert result["code"] == "invalid_title"


@pytest.mark.asyncio
async def test_set_dialog_title_trim_whitespace():
    """Test that title whitespace is trimmed."""
    # Arrange
    mock_project = Mock()
    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Act
    result = await tool._arun(title="  Title with spaces  ")

    # Assert
    assert result["type"] == "success"
    assert result["title"] == "Title with spaces"
    mock_project.upsert_dialog_meta.assert_called_once_with(
        "test_dialog_id", title="Title with spaces"
    )


@pytest.mark.asyncio
async def test_set_dialog_title_long_title_returns_error():
    """Test that very long titles return an error."""
    # Arrange
    mock_project = Mock()
    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Create a title longer than 50 characters
    long_title = "A" * 60

    # Act
    result = await tool._arun(title=long_title)

    # Assert
    assert result["type"] == "tool_error"
    assert result["code"] == "title_too_long"
    assert "60 characters" in result["error"]
    assert "50 characters" in result["error"]
    # Check that details are included
    assert "details" in result
    assert result["details"]["title_length"] == 60
    assert result["details"]["max_length"] == 50


@pytest.mark.asyncio
async def test_set_dialog_title_exactly_50_chars():
    """Test that a title with exactly 50 characters succeeds."""
    # Arrange
    mock_project = Mock()
    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Create a title with exactly 50 characters
    exact_title = "A" * 50

    # Act
    result = await tool._arun(title=exact_title)

    # Assert
    assert result["type"] == "success"
    assert result["title"] == exact_title
    assert len(result["title"]) == 50
    mock_project.upsert_dialog_meta.assert_called_once_with(
        "test_dialog_id", title=exact_title
    )


@pytest.mark.asyncio
async def test_set_dialog_title_exception_handling():
    """Test that exceptions during title update are handled."""
    # Arrange
    mock_project = Mock()
    mock_project.upsert_dialog_meta = Mock(side_effect=Exception("Database error"))

    tool = SetDialogTitleTool()
    tool.set_context(mock_project, "test_dialog_id")

    # Act
    result = await tool._arun(title="Title")

    # Assert
    assert result["type"] == "tool_error"
    assert result["code"] == "internal_error"
    assert "Database error" in result["error"]


@pytest.mark.asyncio
async def test_set_dialog_title_is_ephemeral():
    """Test that tool is marked as ephemeral."""
    # Arrange
    tool = SetDialogTitleTool()

    # Assert
    assert tool.ephemeral is True
