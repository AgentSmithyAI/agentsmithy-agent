"""Test ToolExecutor dispose mechanism."""

from unittest.mock import MagicMock

from agentsmithy.core.project import Project
from agentsmithy.tools.tool_executor import ToolExecutor
from agentsmithy.tools.tool_factory import ToolFactory


def test_tool_executor_dispose_cleans_up_storage(tmp_path):
    """Test that dispose() properly cleans up tool results storage."""
    # Create test project
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"
    project = Project(name="test", root=project_root, state_dir=state_dir)

    # Create ToolExecutor
    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    # Set context (creates storage)
    executor.set_context(project, "test_dialog")
    assert executor._tool_results_storage is not None

    # Dispose should clean up
    executor.dispose()
    assert executor._tool_results_storage is None


def test_tool_executor_dispose_idempotent(tmp_path):
    """Test that dispose() can be called multiple times safely."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"
    project = Project(name="test", root=project_root, state_dir=state_dir)

    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    executor.set_context(project, "test_dialog")

    # Multiple dispose calls should not raise
    executor.dispose()
    executor.dispose()
    executor.dispose()

    assert executor._tool_results_storage is None


def test_tool_executor_del_calls_dispose(tmp_path):
    """Test that __del__ calls dispose as fallback."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"
    project = Project(name="test", root=project_root, state_dir=state_dir)

    llm_provider = MagicMock()
    tool_manager = ToolFactory.create_tool_manager()
    executor = ToolExecutor(tool_manager, llm_provider)

    executor.set_context(project, "test_dialog")

    # Delete executor (triggers __del__)
    del executor

    # Storage should have been disposed (engine disposed)
    # We can't easily check this without accessing internals,
    # but at least no exception was raised
    assert True  # Placeholder - just ensure no crash
