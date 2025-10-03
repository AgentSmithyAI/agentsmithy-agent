"""Tests for project_root handling in tools.

This module tests that tools correctly use project_root for resolving
relative paths instead of relying on the current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentsmithy_server.tools.builtin.delete_file import DeleteFileTool
from agentsmithy_server.tools.builtin.list_files import ListFilesTool
from agentsmithy_server.tools.builtin.read_file import ReadFileTool
from agentsmithy_server.tools.builtin.run_command import RunCommandTool
from agentsmithy_server.tools.builtin.write_file import WriteFileTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_write_file_uses_project_root(tmp_path: Path):
    """Test that write_file resolves relative paths against project_root."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    # Change to different directory
    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)

        # Create tool and set project_root
        tool = WriteFileTool()
        tool.set_project_root(str(project_root))

        # Write file with relative path - should go to project_root, not cwd
        result = await _run(tool, path="test.txt", content="hello from project")

        # File should be in project_root, not in other_dir
        assert (project_root / "test.txt").exists()
        assert (project_root / "test.txt").read_text() == "hello from project"
        assert not (other_dir / "test.txt").exists()

        assert result["type"] == "write_file_result"
        assert "test.txt" in result["path"]
    finally:
        os.chdir(original_cwd)


async def test_write_file_absolute_path_unchanged(tmp_path: Path):
    """Test that write_file doesn't change absolute paths."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_file = target_dir / "absolute.txt"

    tool = WriteFileTool()
    tool.set_project_root(str(project_root))

    # Write with absolute path
    result = await _run(tool, path=str(target_file), content="absolute path")

    # File should be at absolute location
    assert target_file.exists()
    assert target_file.read_text() == "absolute path"
    assert result["type"] == "write_file_result"


async def test_read_file_uses_project_root(tmp_path: Path):
    """Test that read_file resolves relative paths against project_root."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()

    # Create file in project_root
    test_file = project_root / "data.txt"
    test_file.write_text("project data")

    # Create file in other_dir with same name
    (other_dir / "data.txt").write_text("other data")

    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)

        tool = ReadFileTool()
        tool.set_project_root(str(project_root))

        # Read with relative path - should read from project_root
        result = await _run(tool, path="data.txt")

        assert result["type"] == "read_file_result"
        assert result["content"] == "project data"
    finally:
        os.chdir(original_cwd)


async def test_list_files_uses_project_root(tmp_path: Path):
    """Test that list_files resolves relative paths against project_root."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "file1.txt").touch()
    (project_root / "file2.txt").touch()

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "other.txt").touch()

    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)

        tool = ListFilesTool()
        tool.set_project_root(str(project_root))

        # List files with relative path "."
        result = await _run(tool, path=".")

        assert result["type"] == "list_files_result"
        items = result["items"]
        # Should list files from project_root, not other_dir
        assert any("file1.txt" in item for item in items)
        assert any("file2.txt" in item for item in items)
        assert not any("other.txt" in item for item in items)
    finally:
        os.chdir(original_cwd)


async def test_run_command_cwd_uses_project_root(tmp_path: Path):
    """Test that run_command resolves relative cwd against project_root."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    subdir = project_root / "subdir"
    subdir.mkdir()

    other_dir = tmp_path / "other"
    other_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)

        tool = RunCommandTool()
        tool.set_project_root(str(project_root))

        # Run command with relative cwd
        import sys

        cmd = f'{sys.executable} -c "import os; print(os.getcwd())"'
        result = await _run(tool, command=cmd, cwd="subdir")

        assert result["type"] == "run_command_result"
        assert result["exit_code"] == 0
        # Command should run in project_root/subdir
        assert "subdir" in result["stdout"]
    finally:
        os.chdir(original_cwd)


async def test_delete_file_uses_project_root(tmp_path: Path):
    """Test that delete_file resolves relative paths against project_root."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    test_file = project_root / "to_delete.txt"
    test_file.write_text("delete me")

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other_file = other_dir / "to_delete.txt"
    other_file.write_text("don't delete me")

    original_cwd = os.getcwd()
    try:
        os.chdir(other_dir)

        tool = DeleteFileTool()
        tool.set_project_root(str(project_root))

        # Delete with relative path
        result = await _run(tool, path="to_delete.txt")

        assert result["type"] == "delete_file_result"
        # File in project_root should be deleted
        assert not test_file.exists()
        # File in other_dir should still exist
        assert other_file.exists()
    finally:
        os.chdir(original_cwd)


async def test_tool_without_project_root_fallback_to_cwd(tmp_path: Path):
    """Test that tools fall back to cwd when project_root is not set."""
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(test_dir)

        # Don't set project_root
        tool = WriteFileTool()

        # Write with relative path - should use cwd
        result = await _run(tool, path="fallback.txt", content="cwd fallback")

        assert result["type"] == "write_file_result"
        assert (test_dir / "fallback.txt").exists()
    finally:
        os.chdir(original_cwd)


async def test_tool_manager_propagates_project_root():
    """Test that ToolManager.set_project_root propagates to all tools."""
    from agentsmithy_server.tools.tool_manager import ToolManager

    manager = ToolManager()
    tool1 = WriteFileTool()
    tool2 = ReadFileTool()

    manager.register(tool1)
    manager.register(tool2)

    # Set project root via manager
    manager.set_project_root("/test/project")

    # Both tools should have project_root set
    assert hasattr(tool1, "_project_root")
    assert tool1._project_root == "/test/project"
    assert hasattr(tool2, "_project_root")
    assert tool2._project_root == "/test/project"
