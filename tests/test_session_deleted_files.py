"""Test that deleted files are properly tracked in session status."""

from pathlib import Path

from agentsmithy.services.versioning import VersioningTracker


def test_session_tracks_deleted_files(tmp_path: Path) -> None:
    """Test that files deleted from workdir appear in session status."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create initial files
    (project_root / "main.py").write_text("print('hello')\n")
    (project_root / "utils.py").write_text("def helper():\n    pass\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Delete a file from working directory
    (project_root / "utils.py").unlink()

    # Get staged files (should include deleted file)
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should find the deleted file
    assert len(staged_files) == 1
    deleted_file = staged_files[0]

    assert deleted_file["path"] == "utils.py"
    assert deleted_file["status"] == "deleted"
    assert deleted_file["additions"] == 0
    assert deleted_file["deletions"] == 2  # Two lines were in the file
    assert deleted_file["base_content"] == "def helper():\n    pass\n"


def test_session_tracks_multiple_deleted_files(tmp_path: Path) -> None:
    """Test that multiple deleted files are all tracked."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create initial files
    (project_root / "file1.txt").write_text("content1\n")
    (project_root / "file2.txt").write_text("content2\n")
    (project_root / "file3.txt").write_text("content3\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Delete two files
    (project_root / "file1.txt").unlink()
    (project_root / "file3.txt").unlink()

    # Get staged files
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should find both deleted files
    assert len(staged_files) == 2
    deleted_paths = {f["path"] for f in staged_files}
    assert deleted_paths == {"file1.txt", "file3.txt"}

    for f in staged_files:
        assert f["status"] == "deleted"
        assert f["additions"] == 0
        assert f["deletions"] > 0


def test_session_deleted_and_modified_files(tmp_path: Path) -> None:
    """Test that both deleted and modified files are tracked."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create initial files
    (project_root / "keep.py").write_text("def keep():\n    pass\n")
    (project_root / "delete.py").write_text("def delete():\n    pass\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Modify one file and delete another
    (project_root / "keep.py").write_text("def keep():\n    return 42\n")
    tracker.stage_file("keep.py")
    (project_root / "delete.py").unlink()

    # Get staged files
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should find both changes
    assert len(staged_files) == 2

    files_by_path = {f["path"]: f for f in staged_files}

    assert "keep.py" in files_by_path
    assert files_by_path["keep.py"]["status"] == "modified"

    assert "delete.py" in files_by_path
    assert files_by_path["delete.py"]["status"] == "deleted"


def test_deleted_file_becomes_ignored_after_checkpoint(tmp_path: Path) -> None:
    """File committed before ignore update shouldn't appear as deleted afterward."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Initial files (spec tracked before ignore exists)
    (project_root / "main.py").write_text("print('hello')\n")
    (project_root / "agentsmithy.spec").write_text("# pyinstaller spec\n")

    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files including spec")

    # Introduce new ignore pattern and delete the spec locally
    (project_root / ".gitignore").write_text("*.spec\n")
    (project_root / "agentsmithy.spec").unlink()

    staged_files = tracker.get_staged_files(include_diff=True)

    # After ignore change, the spec deletion should not show up as staged change
    assert all(f["path"] != "agentsmithy.spec" for f in staged_files)


def test_deleted_files_not_in_index(tmp_path: Path) -> None:
    """Test that deleted files are detected even when not explicitly staged."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create files
    (project_root / "src" / "utils").mkdir(parents=True)
    (project_root / "src" / "utils" / "diff.py").write_text("def diff():\n    pass\n")
    (project_root / "src" / "main.py").write_text("import utils\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial structure")

    # Delete file (without staging the deletion)
    (project_root / "src" / "utils" / "diff.py").unlink()

    # Get staged files
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should detect the deleted file
    deleted_files = [f for f in staged_files if f["status"] == "deleted"]
    assert len(deleted_files) == 1
    assert deleted_files[0]["path"] == "src/utils/diff.py"


def test_deleted_ignored_files_not_tracked(tmp_path: Path) -> None:
    """Test that deleted files matching ignore patterns are not tracked."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create .gitignore
    (project_root / ".gitignore").write_text("*.log\n__pycache__/\n")

    # Create files (some ignored)
    (project_root / "main.py").write_text("print('hello')\n")
    (project_root / "debug.log").write_text("debug info\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Delete all files
    (project_root / "main.py").unlink()
    (project_root / "debug.log").unlink()

    # Get staged files
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should only track deletion of non-ignored file
    assert len(staged_files) == 1
    assert staged_files[0]["path"] == "main.py"
    assert staged_files[0]["status"] == "deleted"


def test_files_deleted_via_shell_command(tmp_path: Path) -> None:
    """Test that files deleted via shell commands (not delete_file tool) are tracked.

    This simulates when agent uses run_terminal_cmd with 'rm -rf' or similar.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create files
    (project_root / "main.py").write_text("print('hello')\n")
    (project_root / "utils.py").write_text("def helper():\n    pass\n")
    (project_root / "config.json").write_text('{"key": "value"}\n')

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Simulate agent running "rm utils.py config.json" via shell
    # (delete files directly without calling delete_file tool)
    import os

    os.remove(project_root / "utils.py")
    os.remove(project_root / "config.json")

    # Get staged files - should detect both deletions
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should find both deleted files
    assert len(staged_files) == 2
    deleted_paths = {f["path"] for f in staged_files}
    assert deleted_paths == {"utils.py", "config.json"}

    for f in staged_files:
        assert f["status"] == "deleted"
        assert f["additions"] == 0
        assert f["deletions"] > 0
        assert f["base_content"] is not None


def test_directory_deleted_via_shell_command(tmp_path: Path) -> None:
    """Test that files in deleted directories are tracked.

    This simulates when agent uses 'rm -rf directory/' via shell.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create directory with files
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text("print('main')\n")
    (project_root / "src" / "utils.py").write_text("def helper():\n    pass\n")
    (project_root / "README.md").write_text("# Project\n")

    # Initialize tracker and create checkpoint
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    tracker.create_checkpoint("Initial files")

    # Simulate agent running "rm -rf src/" via shell
    import shutil

    shutil.rmtree(project_root / "src")

    # Get staged files - should detect all deletions in the directory
    staged_files = tracker.get_staged_files(include_diff=True)

    # Should find both files that were in src/ directory
    assert len(staged_files) == 2
    deleted_paths = {f["path"] for f in staged_files}
    assert deleted_paths == {"src/main.py", "src/utils.py"}

    for f in staged_files:
        assert f["status"] == "deleted"
        assert f["additions"] == 0
        assert f["deletions"] > 0


def test_file_deleted_via_command_then_restored(tmp_path: Path) -> None:
    """Test that file deleted via shell command can be restored from checkpoint."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create files
    (project_root / "keep.py").write_text("# keep this\n")
    (project_root / "victim.py").write_text("# will be deleted\n")

    # Checkpoint 1: both files exist
    tracker = VersioningTracker(str(project_root), dialog_id="test_dialog")
    tracker.ensure_repo()
    cp1 = tracker.create_checkpoint("Both files exist")

    # Delete via shell command (not delete_file tool)
    import os

    os.remove(project_root / "victim.py")

    # Checkpoint 2: file deleted
    tracker.create_checkpoint("File deleted")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # Both files should exist
    assert (project_root / "keep.py").exists()
    assert (project_root / "victim.py").exists()
    assert (project_root / "victim.py").read_text() == "# will be deleted\n"
