"""Tests for ToolExecutor context propagation to tools.

This module tests that ToolExecutor properly propagates project context
to tools via set_context method.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentsmithy.core.project import Project
from agentsmithy.tools.tool_executor import ToolExecutor
from agentsmithy.tools.tool_factory import ToolFactory


def test_tool_executor_set_context_propagates_project_root(tmp_path: Path):
    """Test that ToolExecutor.set_context propagates project root to tools."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create project
    project = Project(
        name="test_project",
        root=project_root,
        state_dir=state_dir,
    )

    # Create ToolExecutor with ToolFactory
    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    # Set context
    executor.set_context(project, "test_dialog")

    # Check that all tools have project_root set
    for tool in tool_manager._tools.values():
        if hasattr(tool, "_project_root"):
            assert tool._project_root == str(project_root)


@pytest.mark.asyncio
async def test_tool_executor_set_context_with_none_project():
    """Test that ToolExecutor.set_context handles None project gracefully."""
    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    # Should not raise exception
    executor.set_context(None, "test_dialog")

    # Tools should not have project_root set (or it should be None)
    for tool in tool_manager._tools.values():
        if hasattr(tool, "_project_root"):
            # Either not set or None
            assert tool._project_root is None or not tool._project_root


@pytest.mark.asyncio
async def test_tool_execution_with_project_root(tmp_path: Path):
    """Test that tools actually use project_root during execution."""
    project_root = tmp_path / "execution_test"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"
    state_dir.mkdir(parents=True)

    project = Project(
        name="execution_test",
        root=project_root,
        state_dir=state_dir,
    )

    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)
    executor.set_context(project, "test_dialog")

    # Execute write_file with relative path
    result = await tool_manager.run_tool(
        "write_to_file", path="executed.txt", content="execution test"
    )

    assert result["type"] == "write_file_result"
    # File should be in project_root
    assert (project_root / "executed.txt").exists()
    assert (project_root / "executed.txt").read_text() == "execution test"


def test_tool_manager_set_dialog_id_propagates():
    """Test that ToolManager.set_dialog_id propagates to all tools."""
    tool_manager = ToolFactory.create_tool_manager()

    dialog_id = "test_dialog_123"
    tool_manager.set_dialog_id(dialog_id)

    # Check all tools have dialog_id set
    for tool in tool_manager._tools.values():
        assert hasattr(tool, "_dialog_id")
        assert tool._dialog_id == dialog_id


def test_multiple_context_updates():
    """Test that context can be updated multiple times."""
    from pathlib import Path

    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    # First context
    project1 = Project(
        name="project1",
        root=Path("/tmp/project1"),
        state_dir=Path("/tmp/project1/.agentsmithy"),
    )
    executor.set_context(project1, "dialog1")

    # Verify first context - project_root is set
    for tool in tool_manager._tools.values():
        if hasattr(tool, "_project_root"):
            assert tool._project_root == "/tmp/project1"

    # Second context
    project2 = Project(
        name="project2",
        root=Path("/tmp/project2"),
        state_dir=Path("/tmp/project2/.agentsmithy"),
    )
    executor.set_context(project2, "dialog2")

    # Verify second context replaced first
    for tool in tool_manager._tools.values():
        if hasattr(tool, "_project_root"):
            assert tool._project_root == "/tmp/project2"
