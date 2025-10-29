"""Tests for checkpoint and transaction functionality."""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        state_dir = project_root / ".agentsmithy"
        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()
        yield project


def test_versioning_tracker_basic(temp_project):
    """Test basic checkpoint creation."""
    dialog_id = "test-dialog-123"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create a test file
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Hello World")

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Test checkpoint")

    assert checkpoint is not None
    assert checkpoint.commit_id
    assert checkpoint.message == "Test checkpoint"


def test_transaction_single_file(temp_project):
    """Test transaction with single file change."""
    dialog_id = "test-dialog-456"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create initial checkpoint
    test_file = temp_project.root / "file1.txt"
    test_file.write_text("Initial content")
    tracker.create_checkpoint("Initial")

    # Start transaction
    tracker.begin_transaction()
    assert tracker.is_transaction_active()

    # Make change
    test_file.write_text("Updated content")
    tracker.track_file_change("file1.txt", "write")

    # Commit transaction
    checkpoint = tracker.commit_transaction()

    assert checkpoint is not None
    assert "Transaction: 1 files" in checkpoint.message
    assert "write: file1.txt" in checkpoint.message
    assert not tracker.is_transaction_active()


def test_transaction_multiple_files(temp_project):
    """Test transaction with multiple file changes."""
    dialog_id = "test-dialog-789"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Start transaction
    tracker.begin_transaction()

    # Create multiple files
    file1 = temp_project.root / "file1.txt"
    file2 = temp_project.root / "file2.txt"
    file3 = temp_project.root / "file3.txt"

    file1.write_text("Content 1")
    file2.write_text("Content 2")
    file3.write_text("Content 3")

    tracker.track_file_change("file1.txt", "write")
    tracker.track_file_change("file2.txt", "write")
    tracker.track_file_change("file3.txt", "write")

    # Commit transaction
    checkpoint = tracker.commit_transaction()

    assert checkpoint is not None
    assert "Transaction: 3 files" in checkpoint.message
    assert "write: file1.txt" in checkpoint.message
    assert "write: file2.txt" in checkpoint.message
    assert "write: file3.txt" in checkpoint.message


def test_transaction_abort(temp_project):
    """Test aborting a transaction."""
    dialog_id = "test-dialog-abort"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Start transaction
    tracker.begin_transaction()
    tracker.track_file_change("file.txt", "write")

    # Abort
    tracker.abort_transaction()

    assert not tracker.is_transaction_active()


def test_list_checkpoints(temp_project):
    """Test listing checkpoints."""
    dialog_id = "test-dialog-list"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create some checkpoints
    file1 = temp_project.root / "file1.txt"
    file1.write_text("Content 1")
    checkpoint1 = tracker.create_checkpoint("Checkpoint 1")

    file2 = temp_project.root / "file2.txt"
    file2.write_text("Content 2")
    checkpoint2 = tracker.create_checkpoint("Checkpoint 2")

    # List checkpoints
    checkpoints = tracker.list_checkpoints()

    # Should have at least 2 checkpoints (plus initial commit)
    assert len(checkpoints) >= 2

    # Find our checkpoints in the list
    checkpoint_ids = [cp.commit_id for cp in checkpoints]
    assert checkpoint1.commit_id in checkpoint_ids
    assert checkpoint2.commit_id in checkpoint_ids

    # Verify chronological order
    idx1 = checkpoint_ids.index(checkpoint1.commit_id)
    idx2 = checkpoint_ids.index(checkpoint2.commit_id)
    assert idx1 < idx2  # checkpoint1 should come before checkpoint2


def test_restore_checkpoint(temp_project):
    """Test restoring to a checkpoint."""
    dialog_id = "test-dialog-restore"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create initial state
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Version 1")
    checkpoint1 = tracker.create_checkpoint("Version 1")

    # Modify file
    test_file.write_text("Version 2")
    tracker.create_checkpoint("Version 2")

    # Verify current state
    assert test_file.read_text() == "Version 2"

    # Restore to checkpoint1
    tracker.restore_checkpoint(checkpoint1.commit_id)

    # Verify restored state
    assert test_file.read_text() == "Version 1"


def test_create_dialog_with_initial_checkpoint(temp_project):
    """Test that creating a dialog creates an initial checkpoint."""
    temp_project.ensure_dialogs_dir()

    # Create a file in project before creating dialog
    (temp_project.root / "existing.txt").write_text("Existing file")

    # Create dialog
    dialog_id = temp_project.create_dialog(title="Test Dialog")

    # Verify dialog metadata has initial checkpoint
    index = temp_project.load_dialogs_index()
    dialog_meta = None
    for dialog in index.get("dialogs", []):
        if dialog.get("id") == dialog_id:
            dialog_meta = dialog
            break

    assert dialog_meta is not None
    assert "initial_checkpoint" in dialog_meta
    assert dialog_meta["initial_checkpoint"]

    # Verify checkpoint exists
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    checkpoints = tracker.list_checkpoints()

    # Should have at least the initial checkpoint
    assert len(checkpoints) >= 1

    # Verify that the initial checkpoint is in the list
    checkpoint_ids = [cp.commit_id for cp in checkpoints]
    assert dialog_meta["initial_checkpoint"] in checkpoint_ids


def test_transaction_with_custom_message(temp_project):
    """Test transaction with custom commit message."""
    dialog_id = "test-dialog-custom"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    tracker.begin_transaction()
    tracker.track_file_change("file.txt", "write")

    # Commit with custom message
    checkpoint = tracker.commit_transaction("Custom message for this transaction")

    assert checkpoint is not None
    assert checkpoint.message == "Custom message for this transaction"


def test_gitignore_respected_in_checkpoint(temp_project):
    """Test that .gitignore patterns are respected when creating checkpoints."""
    dialog_id = "test-dialog-gitignore"

    # Create .gitignore
    gitignore = temp_project.root / ".gitignore"
    gitignore.write_text("ignored_dir/\n*.log\ndist/\n")

    # Create various files
    (temp_project.root / "tracked.txt").write_text("This should be tracked")
    (temp_project.root / "test.log").write_text("This should be ignored")

    ignored_dir = temp_project.root / "ignored_dir"
    ignored_dir.mkdir()
    (ignored_dir / "secret.txt").write_text("This should be ignored")

    dist_dir = temp_project.root / "dist"
    dist_dir.mkdir()
    (dist_dir / "binary").write_text("This should be ignored")

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()
    checkpoint = tracker.create_checkpoint("Test checkpoint")

    # Verify checkpoint was created
    assert checkpoint is not None

    # Verify .gitignore patterns were applied by checking tree
    repo = tracker.ensure_repo()
    commit_obj = repo[checkpoint.commit_id.encode()]
    tree = repo[commit_obj.tree]

    # Check which files are in the tree
    tracked_files = []
    for entry in tree.items():
        name = entry[0].decode("utf-8")
        tracked_files.append(name)

    # Should include tracked.txt
    assert "tracked.txt" in tracked_files

    # Should NOT include ignored files
    assert "test.log" not in tracked_files
    assert not any("ignored_dir" in f for f in tracked_files)
    assert not any("dist/" in f for f in tracked_files)
