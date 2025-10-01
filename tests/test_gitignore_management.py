"""Tests for .gitignore management in projects."""

from __future__ import annotations

from pathlib import Path

from agentsmithy_server.core.project import Project


def test_ensure_gitignore_entry_creates_new_file(tmp_path: Path):
    """Test that ensure_gitignore_entry creates .gitignore if it doesn't exist."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check that .gitignore was created
    gitignore = project_root / ".gitignore"
    assert gitignore.exists()

    # Check content
    content = gitignore.read_text(encoding="utf-8")
    assert ".agentsmithy" in content
    assert content == ".agentsmithy\n"


def test_ensure_gitignore_entry_appends_to_existing(tmp_path: Path):
    """Test that ensure_gitignore_entry appends to existing .gitignore."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create existing .gitignore
    gitignore = project_root / ".gitignore"
    gitignore.write_text("node_modules/\n*.log\n", encoding="utf-8")

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check content
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert "node_modules/" in lines
    assert "*.log" in lines
    assert ".agentsmithy" in lines
    assert lines[-1] == ".agentsmithy"


def test_ensure_gitignore_entry_does_not_duplicate(tmp_path: Path):
    """Test that ensure_gitignore_entry doesn't add duplicate entries."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create .gitignore with entry already present
    gitignore = project_root / ".gitignore"
    gitignore.write_text("node_modules/\n.agentsmithy\n*.log\n", encoding="utf-8")

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check that entry wasn't duplicated
    content = gitignore.read_text(encoding="utf-8")
    count = content.count(".agentsmithy")
    assert count == 1


def test_ensure_gitignore_entry_handles_trailing_slash(tmp_path: Path):
    """Test that ensure_gitignore_entry recognizes entry with trailing slash."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create .gitignore with entry with trailing slash
    gitignore = project_root / ".gitignore"
    gitignore.write_text(".agentsmithy/\n", encoding="utf-8")

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check that entry wasn't duplicated
    content = gitignore.read_text(encoding="utf-8")
    # Should still have only one entry (the one with trailing slash)
    assert content.count("agentsmithy") == 1


def test_ensure_gitignore_entry_handles_no_trailing_newline(tmp_path: Path):
    """Test that ensure_gitignore_entry handles files without trailing newline."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create .gitignore without trailing newline
    gitignore = project_root / ".gitignore"
    gitignore.write_text("node_modules/", encoding="utf-8")  # No \n at end

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check content - should have newline added before our entry
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert "node_modules/" in lines
    assert ".agentsmithy" in lines
    # Should end with newline
    assert content.endswith("\n")


def test_ensure_gitignore_entry_ignores_whitespace(tmp_path: Path):
    """Test that ensure_gitignore_entry ignores leading/trailing whitespace."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    # Create .gitignore with entry with whitespace
    gitignore = project_root / ".gitignore"
    gitignore.write_text("  .agentsmithy  \n", encoding="utf-8")

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Call ensure_gitignore_entry
    project.ensure_gitignore_entry()

    # Check that entry wasn't duplicated (whitespace should be ignored)
    content = gitignore.read_text(encoding="utf-8")
    assert content.count("agentsmithy") == 1


def test_ensure_gitignore_entry_called_on_startup(tmp_path: Path):
    """Test that ensure_state_dir and ensure_gitignore_entry work together."""
    project_root = tmp_path / "new_project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    project = Project(
        name="new_project",
        root=project_root,
        state_dir=state_dir,
    )

    # Call both methods as done in main.py
    project.ensure_state_dir()
    project.ensure_gitignore_entry()

    # Check that both state dir and gitignore were created
    assert state_dir.exists()
    assert (project_root / ".gitignore").exists()
    assert ".agentsmithy" in (project_root / ".gitignore").read_text()


def test_ensure_gitignore_entry_fails_gracefully_on_permission_error(tmp_path: Path):
    """Test that ensure_gitignore_entry fails gracefully on errors."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = project_root / ".agentsmithy"

    project = Project(
        name="test",
        root=project_root,
        state_dir=state_dir,
    )

    # Make project root read-only
    project_root.chmod(0o555)

    try:
        # Should not raise exception
        project.ensure_gitignore_entry()
        # If it didn't raise, that's good
        assert True
    finally:
        # Restore permissions for cleanup
        project_root.chmod(0o755)
