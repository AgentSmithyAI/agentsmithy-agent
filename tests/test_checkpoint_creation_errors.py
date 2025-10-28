"""Tests for checkpoint creation error handling.

Ensures that errors during checkpoint creation are properly propagated
and not silently swallowed.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


def test_checkpoint_creation_with_unreadable_file(tmp_path: Path):
    """Test that checkpoint creation fails if a file cannot be read."""
    # Create a project with a file
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create a normal file
    normal_file = project_root / "normal.txt"
    normal_file.write_text("hello")

    # Create a file and then make it unreadable by patching read_bytes
    unreadable_file = project_root / "unreadable.txt"
    unreadable_file.write_text("secret")

    # Create tracker and try to create checkpoint
    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    # Patch read_bytes to fail for unreadable.txt
    original_read_bytes = Path.read_bytes

    def mock_read_bytes(self):
        if self.name == "unreadable.txt":
            raise PermissionError(f"Permission denied: {self}")
        return original_read_bytes(self)

    with patch.object(Path, "read_bytes", mock_read_bytes):
        # Should raise RuntimeError with details about failed files
        with pytest.raises(RuntimeError) as exc_info:
            tracker.create_checkpoint("Test checkpoint")

        error_msg = str(exc_info.value)
        assert "Failed to process" in error_msg
        assert "file(s) during checkpoint creation" in error_msg
        assert "unreadable.txt" in error_msg
        assert "Permission denied" in error_msg


def test_checkpoint_creation_with_multiple_unreadable_files(tmp_path: Path):
    """Test that checkpoint creation reports multiple failed files."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create multiple files
    for i in range(10):
        (project_root / f"file{i}.txt").write_text(f"content{i}")

    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    # Patch to fail on specific files
    original_read_bytes = Path.read_bytes

    def mock_read_bytes(self):
        # Fail on file2, file5, file7
        if self.name in ["file2.txt", "file5.txt", "file7.txt"]:
            raise OSError(f"IO error: {self.name}")
        return original_read_bytes(self)

    with patch.object(Path, "read_bytes", mock_read_bytes):
        with pytest.raises(RuntimeError) as exc_info:
            tracker.create_checkpoint("Test checkpoint")

        error_msg = str(exc_info.value)
        # Should mention 3 failed files
        assert "Failed to process 3 file(s)" in error_msg
        # Should list the files
        assert "file2.txt" in error_msg
        assert "file5.txt" in error_msg
        assert "file7.txt" in error_msg


def test_checkpoint_creation_error_truncates_long_error_list(tmp_path: Path):
    """Test that long error lists are truncated in error message."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create 20 files
    for i in range(20):
        (project_root / f"file{i}.txt").write_text(f"content{i}")

    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    # Patch to fail on all files
    with patch.object(Path, "read_bytes", side_effect=OSError("Failed")):
        with pytest.raises(RuntimeError) as exc_info:
            tracker.create_checkpoint("Test checkpoint")

        error_msg = str(exc_info.value)
        # Should mention all 20 failed files
        assert "Failed to process 20 file(s)" in error_msg
        # Should truncate to first 5
        assert "... and 15 more" in error_msg


def test_create_dialog_rolls_back_on_checkpoint_failure(tmp_path: Path):
    """Test that dialog creation is rolled back if checkpoint creation fails."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create a file that will fail to read
    bad_file = project_root / "bad.txt"
    bad_file.write_text("content")

    # Create project
    state_dir = project_root / ".agentsmithy"
    project = Project(
        name="test_project",
        root=project_root,
        state_dir=state_dir,
    )
    project.ensure_state_dir()

    # Patch read_bytes to fail
    with patch.object(Path, "read_bytes", side_effect=PermissionError("Access denied")):
        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            project.create_dialog(title="Test Dialog")

        assert "Failed to create dialog" in str(exc_info.value)

    # Verify dialog was NOT created
    index = project.load_dialogs_index()
    assert len(index.get("dialogs", [])) == 0
    assert index.get("current_dialog_id") is None

    # Verify dialog directory was cleaned up (no dialog subdirectories)
    dialogs_dir = state_dir / "dialogs"
    if dialogs_dir.exists():
        # Should have no dialog subdirectories (index.json is ok)
        dialog_subdirs = [d for d in dialogs_dir.iterdir() if d.is_dir()]
        assert len(dialog_subdirs) == 0


def test_create_dialog_success_with_readable_files(tmp_path: Path):
    """Test that dialog creation succeeds when all files are readable."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create some normal files
    (project_root / "file1.txt").write_text("content1")
    (project_root / "file2.txt").write_text("content2")

    # Create project
    state_dir = project_root / ".agentsmithy"
    project = Project(
        name="test_project",
        root=project_root,
        state_dir=state_dir,
    )
    project.ensure_state_dir()

    # Should succeed
    dialog_id = project.create_dialog(title="Test Dialog")

    # Verify dialog was created
    assert dialog_id is not None
    index = project.load_dialogs_index()
    assert len(index.get("dialogs", [])) == 1
    assert index["dialogs"][0]["id"] == dialog_id
    assert index["dialogs"][0]["title"] == "Test Dialog"

    # Verify checkpoint was created
    assert "initial_checkpoint" in index["dialogs"][0]
    assert "active_session" in index["dialogs"][0]

    # Verify dialog directory exists
    dialog_dir = state_dir / "dialogs" / dialog_id
    assert dialog_dir.exists()
    checkpoint_dir = dialog_dir / "checkpoints"
    assert checkpoint_dir.exists()


def test_checkpoint_creation_logs_failures(tmp_path: Path, caplog):
    """Test that checkpoint creation logs error details."""
    import logging

    caplog.set_level(logging.ERROR)

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "file.txt").write_text("content")

    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    with patch.object(Path, "read_bytes", side_effect=OSError("Disk error")):
        with pytest.raises(RuntimeError):
            tracker.create_checkpoint("Test")

    # Verify error was logged
    assert any(
        "Failed to process files during checkpoint creation" in record.message
        for record in caplog.records
    )


def test_partial_checkpoint_not_created_on_error(tmp_path: Path):
    """Test that no partial checkpoint is created when some files fail."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create multiple files
    (project_root / "good.txt").write_text("ok")
    (project_root / "bad.txt").write_text("fail")

    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    # Patch to fail on bad.txt
    original_read_bytes = Path.read_bytes

    def mock_read_bytes(self):
        if self.name == "bad.txt":
            raise OSError("Bad file")
        return original_read_bytes(self)

    with patch.object(Path, "read_bytes", mock_read_bytes):
        with pytest.raises(RuntimeError):
            tracker.create_checkpoint("Partial checkpoint")

    # Verify no checkpoint was created
    checkpoints = tracker.list_checkpoints()
    assert len(checkpoints) == 0


def test_blob_reuse_handles_decompression_errors(tmp_path: Path):
    """Test that decompression errors from project git are handled gracefully."""
    from unittest.mock import MagicMock

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "test.txt").write_text("content")

    tracker = VersioningTracker(str(project_root), "test_dialog")
    tracker.ensure_repo()

    # Mock project git repo with blob that fails on decompression
    mock_blob = MagicMock()
    # Accessing .data should raise decompression error
    type(mock_blob).data = property(
        lambda self: (_ for _ in ()).throw(
            Exception("Error -3 while decompressing data: unknown compression method")
        )
    )

    mock_repo = MagicMock()
    mock_repo.__getitem__.return_value = mock_blob

    mock_tree = MagicMock()
    mock_tree.lookup_path.return_value = (0o100644, b"fake_sha")

    # Should fallback to reading file from disk instead of failing
    blob = tracker._try_reuse_blob(
        project_root / "test.txt", "test.txt", mock_repo, mock_tree
    )

    # Should return None (fallback to reading file)
    assert blob is None
