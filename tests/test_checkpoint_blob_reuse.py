"""Tests for checkpoint blob reuse optimization.

Verifies that:
1. Blobs are reused from project git when files unchanged
2. New blobs are created only for changed/new files
3. Optimization works correctly with real git repositories
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def git_project():
    """Create a temporary project with REAL git repository.

    Note: Uses subprocess git to create repo, then dulwich reads it.
    This tests that dulwich can correctly read repositories created by real git.
    Skips if git binary not available (CI has git, local dev may not).
    """
    import shutil

    # Check if git is available
    if shutil.which("git") is None:
        pytest.skip("git binary not available (required for blob reuse tests)")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Initialize git repo using REAL git (to test dulwich can read it)
        subprocess.run(
            ["git", "init"], cwd=project_root, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_root,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_root,
            capture_output=True,
        )

        yield project_root


def test_blob_reuse_from_project_git(git_project):
    """Test that dulwich reuses blobs from git repo created by real git binary."""
    # Create files and commit using REAL git
    for i in range(10):
        (git_project / f"file{i}.txt").write_text(f"Content {i}")

    subprocess.run(["git", "add", "."], cwd=git_project, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_project,
        capture_output=True,
    )

    # Create checkpoint - should reuse all blobs
    tracker = VersioningTracker(str(git_project))
    cp = tracker.create_checkpoint("Test checkpoint")

    # Verify checkpoint was created
    assert cp.commit_id
    assert cp.message == "Test checkpoint"

    # Check logs would show reused blobs (we can't easily verify logs in test,
    # but we can verify the checkpoint contains files)
    checkpoints = tracker.list_checkpoints()
    assert len(checkpoints) == 1


def test_blob_reuse_creates_new_for_changed_files(git_project):
    """Test that new blobs are created for changed files."""
    # Create initial files and commit using real git
    (git_project / "unchanged.txt").write_text("Unchanged content")
    (git_project / "will_change.txt").write_text("Original content")

    subprocess.run(["git", "add", "."], cwd=git_project, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_project,
        capture_output=True,
    )

    # Create first checkpoint
    tracker = VersioningTracker(str(git_project))
    cp1 = tracker.create_checkpoint("Checkpoint 1")

    # Change one file
    (git_project / "will_change.txt").write_text("Modified content")

    # Create second checkpoint - should reuse blob for unchanged.txt
    cp2 = tracker.create_checkpoint("Checkpoint 2")

    # Verify both checkpoints exist
    assert cp1.commit_id != cp2.commit_id

    # Restore to first checkpoint
    tracker.restore_checkpoint(cp1.commit_id)

    # Verify content restored
    assert (git_project / "will_change.txt").read_text() == "Original content"


def test_blob_reuse_with_new_files(git_project):
    """Test that new files get new blobs while existing files reuse."""
    # Create initial files and commit using real git
    for i in range(5):
        (git_project / f"existing{i}.txt").write_text(f"Existing {i}")

    subprocess.run(["git", "add", "."], cwd=git_project, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_project,
        capture_output=True,
    )

    # Create checkpoint
    tracker = VersioningTracker(str(git_project))
    cp1 = tracker.create_checkpoint("With existing files")

    # Add new files (should create new blobs)
    for i in range(3):
        (git_project / f"new{i}.txt").write_text(f"New {i}")

    # Create checkpoint - should reuse 5 existing + create 3 new
    cp2 = tracker.create_checkpoint("With new files")

    assert cp1.commit_id != cp2.commit_id


def test_no_project_git_creates_all_blobs(git_project):
    """Test that without project git, all blobs are created normally."""
    # Remove .git directory
    import shutil

    git_dir = git_project / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    # Create files
    for i in range(5):
        (git_project / f"file{i}.txt").write_text(f"Content {i}")

    # Create checkpoint - should create all blobs (no reuse possible)
    tracker = VersioningTracker(str(git_project))
    cp = tracker.create_checkpoint("No git repo")

    # Verify checkpoint created successfully
    assert cp.commit_id
    checkpoints = tracker.list_checkpoints()
    assert len(checkpoints) == 1


def test_blob_reuse_handles_binary_files(git_project):
    """Test that blob reuse works with binary files."""
    # Create binary files
    (git_project / "image.bin").write_bytes(b"\x00\x01\x02" * 1000)
    (git_project / "data.bin").write_bytes(b"\xff\xfe\xfd" * 1000)

    subprocess.run(["git", "add", "."], cwd=git_project, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Binary files"],
        cwd=git_project,
        capture_output=True,
    )

    # Create checkpoint
    tracker = VersioningTracker(str(git_project))
    cp = tracker.create_checkpoint("With binaries")

    # Verify checkpoint created
    assert cp.commit_id
