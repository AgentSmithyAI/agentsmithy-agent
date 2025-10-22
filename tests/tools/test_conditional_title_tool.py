"""Tests for conditional set_dialog_title tool registration."""

from unittest.mock import AsyncMock, Mock

import pytest

from agentsmithy.agents.universal_agent import UniversalAgent


@pytest.mark.asyncio
async def test_title_tool_stays_when_no_title(monkeypatch):
    """Test that set_dialog_title tool stays when title is None."""
    # Arrange
    mock_llm = Mock()
    mock_llm.get_model_name = Mock(return_value="test-model")
    mock_llm.agenerate = AsyncMock(return_value="test response")

    mock_context_builder = Mock()
    mock_context_builder.build_context = AsyncMock(return_value={})
    mock_context_builder.format_context_for_prompt = Mock(return_value="")

    agent = UniversalAgent(mock_llm, mock_context_builder)

    # Mock tool executor to avoid actual execution
    agent.tool_executor.set_context = Mock()  # Disable set_context to avoid path issues
    agent.tool_executor.process_with_tools_async = AsyncMock(
        return_value={"type": "text", "content": "response"}
    )

    # Tool should be in registry by default
    assert agent.tool_manager.has_tool("set_dialog_title") is True

    context = {
        "dialog": {"id": "test_id", "title": None},  # No title
        "project": None,  # No project to avoid path issues
    }

    # Act
    await agent.process("test query", context)

    # Assert - tool should still be present (not removed)
    assert agent.tool_manager.has_tool("set_dialog_title") is True


@pytest.mark.asyncio
async def test_title_tool_removed_when_title_set(monkeypatch):
    """Test that set_dialog_title tool is removed when title is set."""
    # Arrange
    mock_llm = Mock()
    mock_llm.get_model_name = Mock(return_value="test-model")
    mock_llm.agenerate = AsyncMock(return_value="test response")

    mock_context_builder = Mock()
    mock_context_builder.build_context = AsyncMock(return_value={})
    mock_context_builder.format_context_for_prompt = Mock(return_value="")

    agent = UniversalAgent(mock_llm, mock_context_builder)

    # Mock tool executor
    agent.tool_executor.set_context = Mock()  # Disable set_context
    agent.tool_executor.process_with_tools_async = AsyncMock(
        return_value={"type": "text", "content": "response"}
    )

    # First, manually add the tool (simulate it was there from previous call)
    from agentsmithy.tools.builtin.set_dialog_title import SetDialogTitleTool

    agent.tool_manager.register(SetDialogTitleTool())
    assert agent.tool_manager.has_tool("set_dialog_title") is True

    context = {
        "dialog": {"id": "test_id", "title": "Existing Title"},  # Title is set
        "project": None,
    }

    # Act
    await agent.process("test query", context)

    # Assert - tool should be removed
    assert agent.tool_manager.has_tool("set_dialog_title") is False


@pytest.mark.asyncio
async def test_title_tool_stays_when_no_title_multiple_calls(monkeypatch):
    """Test that set_dialog_title tool stays registered across multiple calls without title."""
    # Arrange
    mock_llm = Mock()
    mock_llm.get_model_name = Mock(return_value="test-model")
    mock_llm.agenerate = AsyncMock(return_value="test response")

    mock_context_builder = Mock()
    mock_context_builder.build_context = AsyncMock(return_value={})
    mock_context_builder.format_context_for_prompt = Mock(return_value="")

    agent = UniversalAgent(mock_llm, mock_context_builder)

    agent.tool_executor.set_context = Mock()  # Disable set_context
    agent.tool_executor.process_with_tools_async = AsyncMock(
        return_value={"type": "text", "content": "response"}
    )

    # Tool should be in registry by default
    assert agent.tool_manager.has_tool("set_dialog_title") is True

    context = {
        "dialog": {"id": "test_id", "title": None},
        "project": None,
    }

    # Act - call multiple times
    await agent.process("query 1", context)
    assert agent.tool_manager.has_tool("set_dialog_title") is True

    await agent.process("query 2", context)
    assert agent.tool_manager.has_tool("set_dialog_title") is True


@pytest.mark.asyncio
async def test_title_tool_in_initial_registry():
    """Test that set_dialog_title is in the default registry."""
    from agentsmithy.tools.build_registry import build_registry

    registry = build_registry()

    # Assert - tool should be in default registry
    assert registry.has_tool("set_dialog_title") is True


@pytest.mark.asyncio
async def test_title_tool_stays_when_empty_string_title(monkeypatch):
    """Test that set_dialog_title tool stays when title is empty string."""
    # Arrange
    mock_llm = Mock()
    mock_llm.get_model_name = Mock(return_value="test-model")
    mock_llm.agenerate = AsyncMock(return_value="test response")

    mock_context_builder = Mock()
    mock_context_builder.build_context = AsyncMock(return_value={})
    mock_context_builder.format_context_for_prompt = Mock(return_value="")

    agent = UniversalAgent(mock_llm, mock_context_builder)

    agent.tool_executor.set_context = Mock()  # Disable set_context
    agent.tool_executor.process_with_tools_async = AsyncMock(
        return_value={"type": "text", "content": "response"}
    )

    # Tool should be in registry by default
    assert agent.tool_manager.has_tool("set_dialog_title") is True

    context = {
        "dialog": {"id": "test_id", "title": ""},  # Empty string
        "project": None,
    }

    # Act
    await agent.process("test query", context)

    # Assert - tool should stay (empty string is treated as no title)
    assert agent.tool_manager.has_tool("set_dialog_title") is True
