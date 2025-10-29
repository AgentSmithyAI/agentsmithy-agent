"""Test that reset/restore removes ignored files that weren't in checkpoint."""

import tempfile
from pathlib import Path

from agentsmithy.services.versioning import VersioningTracker


def test_reset_removes_newly_created_ignored_files():
    """Reset should remove ignored files that were created after checkpoint.

    Bug scenario:
    1. Create checkpoint (without .venv because it's in DEFAULT_EXCLUDES)
    2. Agent creates .venv/lib/site-packages/package.py
    3. User calls restore (reset)
    4. Expected: .venv should be deleted
    5. Actual (bug): files remain because they're ignored
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-reset-ignored"

        # Create initial files
        (project_root / "main.py").write_text("# main")
        (project_root / "README.md").write_text("# README")

        # Create initial checkpoint
        tracker = VersioningTracker(str(project_root), dialog_id)
        tracker.ensure_repo()
        checkpoint1 = tracker.create_checkpoint("Initial checkpoint")

        # Verify .venv is in DEFAULT_EXCLUDES
        from agentsmithy.services.versioning import DEFAULT_EXCLUDES

        has_venv_exclude = any(".venv" in p for p in DEFAULT_EXCLUDES)
        assert has_venv_exclude, ".venv should be in DEFAULT_EXCLUDES"

        # Now "agent" creates .venv/lib/package.py
        venv_dir = project_root / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        package_file = venv_dir / "package.py"
        package_file.write_text("# package\n")

        # Stage file (emulate what write_file tool does)
        tracker.stage_file(".venv/lib/package.py")

        # Create checkpoint 2 (file will be force-added despite being ignored)
        tracker.create_checkpoint("Added .venv file")

        # Verify file exists
        assert package_file.exists(), "Package file should exist before reset"

        # Call restore (reset functionality) - restore to checkpoint 1 (before .venv)
        tracker.restore_checkpoint(checkpoint1.commit_id)

        # BUG: File should be deleted because it wasn't in the checkpoint
        assert not package_file.exists(), (
            "Package file should be deleted by restore "
            "(it was created after checkpoint and wasn't in it)"
        )
        assert not venv_dir.exists(), ".venv/lib dir should be deleted"


def test_restore_removes_newly_created_ignored_files():
    """Restore should also remove ignored files that were created after checkpoint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-restore-ignored"

        # Create initial files
        (project_root / "main.py").write_text("# main")

        # Create checkpoint 1
        tracker = VersioningTracker(str(project_root), dialog_id)
        tracker.ensure_repo()
        checkpoint1 = tracker.create_checkpoint("Checkpoint 1")

        # Modify main.py and create .venv
        (project_root / "main.py").write_text("# main modified")
        venv_dir = project_root / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        package_file = venv_dir / "package.py"
        package_file.write_text("# package\n")

        # Stage file (emulate what write_file tool does)
        tracker.stage_file(".venv/lib/package.py")

        # Create checkpoint 2
        tracker.create_checkpoint("Checkpoint 2 with changes")

        # Now restore to checkpoint 1
        tracker.restore_checkpoint(checkpoint1.commit_id)

        # Both main.py should be restored AND .venv should be deleted
        assert (project_root / "main.py").read_text() == "# main"
        assert not package_file.exists(), (
            "Package file should be deleted by restore " "(it wasn't in checkpoint 1)"
        )


def test_reset_preserves_ignored_files_that_existed_before():
    """Reset should NOT delete ignored files that already existed and user wants to keep.

    This is to make sure we don't break the opposite case.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-preserve-ignored"

        # Create files including .venv BEFORE checkpoint
        (project_root / "main.py").write_text("# main")
        venv_dir = project_root / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        original_package = venv_dir / "original.py"
        original_package.write_text("# original package\n")

        # Create checkpoint (won't include .venv because it's ignored)
        tracker = VersioningTracker(str(project_root), dialog_id)
        tracker.ensure_repo()
        checkpoint1 = tracker.create_checkpoint("With existing .venv")

        # Modify main.py
        (project_root / "main.py").write_text("# main modified")

        # Reset (restore)
        tracker.restore_checkpoint(checkpoint1.commit_id)

        # main.py should be reset, but .venv should remain
        # (because it existed before and wasn't tracked)
        assert (project_root / "main.py").read_text() == "# main"
        assert original_package.exists(), (
            "Original package should remain "
            "(existed before checkpoint, user likely wants to keep it)"
        )
