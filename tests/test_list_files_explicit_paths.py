"""
Test that list_files shows contents of explicitly requested directories,
even if those directories would normally be ignored (like .github).
"""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.tools.builtin.list_files import ListFilesTool


@pytest.mark.asyncio
async def test_list_github_directory_explicitly():
    """Test that .github contents are shown when explicitly requested."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test workspace
        workspace = tmpdir / "test_workspace"
        workspace.mkdir()

        # Create .github directory with files
        github_dir = workspace / ".github"
        github_dir.mkdir()
        (github_dir / "workflow.yml").write_text("test")
        (github_dir / "action.yml").write_text("test")

        workflows = github_dir / "workflows"
        workflows.mkdir()
        (workflows / "ci.yml").write_text("test")
        (workflows / "deploy.yml").write_text("test")

        # Create a .git directory (should be filtered even in .github)
        git_dir = github_dir / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("test")

        # Create node_modules (should be filtered even in .github)
        node_modules = github_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("test")

        # Create the tool
        tool = ListFilesTool()
        tool._project_root = str(workspace)

        # Test 1: List .github directory explicitly (non-recursive)
        result = await tool._arun(path=str(github_dir), recursive=False)

        assert result["type"] == "list_files_result"
        assert result["path"] == str(github_dir)

        items = [Path(item).name for item in result["items"]]

        # Should show regular files and workflows directory
        assert "workflow.yml" in items
        assert "action.yml" in items
        assert "workflows" in items

        # Should NOT show ignored directories
        assert ".git" not in items
        assert "node_modules" not in items

        assert len(items) == 3

        # Test 2: List .github directory explicitly (recursive)
        result2 = await tool._arun(path=str(github_dir), recursive=True)

        items2 = [str(Path(item).relative_to(github_dir)) for item in result2["items"]]

        # Should show all files including those in workflows/
        assert "workflow.yml" in items2
        assert "action.yml" in items2
        assert "workflows" in items2
        assert "workflows/ci.yml" in items2 or "workflows\\ci.yml" in items2
        assert "workflows/deploy.yml" in items2 or "workflows\\deploy.yml" in items2

        # Should NOT show files in ignored subdirectories
        assert not any(".git" in item for item in items2)
        assert not any("node_modules" in item for item in items2)


@pytest.mark.asyncio
async def test_list_files_ignores_github_in_parent():
    """Test that .github is ignored when listing parent directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test workspace
        workspace = tmpdir / "test_workspace"
        workspace.mkdir()

        # Create .github directory
        github_dir = workspace / ".github"
        github_dir.mkdir()
        (github_dir / "workflow.yml").write_text("test")

        # Create regular directory
        src_dir = workspace / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("test")

        # Create the tool
        tool = ListFilesTool()
        tool._project_root = str(workspace)

        # List workspace root - should NOT show .github (it's hidden)
        result = await tool._arun(
            path=str(workspace), recursive=False, hidden_files=False
        )

        items = [Path(item).name for item in result["items"]]

        # Should show src but not .github
        assert "src" in items
        assert ".github" not in items


@pytest.mark.asyncio
async def test_list_files_ignores_github_even_with_hidden_flag():
    """Test that .github is still ignored even with hidden_files=True.

    The .github directory is in DEFAULT_IGNORE_DIRS, so it's filtered out
    even when hidden_files=True. To see .github contents, the user must
    explicitly request that directory as the path.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test workspace
        workspace = tmpdir / "test_workspace"
        workspace.mkdir()

        # Create .github directory (in DEFAULT_IGNORE_DIRS)
        github_dir = workspace / ".github"
        github_dir.mkdir()
        (github_dir / "workflow.yml").write_text("test")

        # Create .env directory (in DEFAULT_IGNORE_DIRS)
        env_dir = workspace / ".env"
        env_dir.mkdir()
        (env_dir / "secrets").write_text("test")

        # Create regular hidden directory (NOT in DEFAULT_IGNORE_DIRS)
        hidden_dir = workspace / ".config"
        hidden_dir.mkdir()
        (hidden_dir / "config.yml").write_text("test")

        # Create regular directory
        src_dir = workspace / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("test")

        # Create the tool
        tool = ListFilesTool()
        tool._project_root = str(workspace)

        # List workspace root with hidden_files=True
        result = await tool._arun(
            path=str(workspace), recursive=False, hidden_files=True
        )

        items = [Path(item).name for item in result["items"]]

        # Should show src and regular hidden directories
        assert "src" in items
        assert ".config" in items

        # Should NOT show directories in DEFAULT_IGNORE_DIRS
        assert ".github" not in items
        assert ".env" not in items
