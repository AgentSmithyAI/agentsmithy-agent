"""Test that blob reuse optimization avoids reading unchanged files.

This test verifies that the blob reuse optimization works correctly:
1. For UNCHANGED files (same size + same hash in project git) - blob is reused WITHOUT reading file content
2. For CHANGED files (same size but different content) - file IS read to detect size collision

This prevents regression where we accidentally read all files even when they haven't changed.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


def test_blob_reuse_does_not_read_unchanged_files():
    """Test that unchanged files are reused without reading content (optimization works)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        # Create a main git repo to simulate user's project git (before creating dialog)
        subprocess.run(
            ["git", "init"], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Create .gitignore to exclude .agentsmithy
        gitignore = project_root / ".gitignore"
        gitignore.write_text(".agentsmithy/\n")

        # Create file and commit to project git
        file_path = project_root / "unchanged.py"
        content = "def hello():\n    return 'world'\n"
        file_path.write_text(content)

        # Create dialog after git init (this creates .agentsmithy)
        dialog_id = project.create_dialog(title="Test Dialog")

        subprocess.run(
            ["git", "add", "."], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Wait for mtime to be "old enough" (>1s) for optimization to kick in
        import time

        time.sleep(1.1)

        tracker = VersioningTracker(str(project_root), dialog_id)

        # Track file reads (both read_bytes and open calls for streaming)
        original_read_bytes = Path.read_bytes
        original_open = open
        file_reads = []

        def tracked_read_bytes(self):
            file_reads.append(("read_bytes", str(self)))
            return original_read_bytes(self)

        def tracked_open(file_path, *args, **kwargs):
            file_reads.append(("open", str(file_path)))
            return original_open(file_path, *args, **kwargs)

        # Create checkpoint with tracked file access
        with patch.object(Path, "read_bytes", tracked_read_bytes):
            with patch("builtins.open", tracked_open):
                _ = tracker.create_checkpoint("Checkpoint 1")

        # Verify: unchanged.py should NOT be read (mtime optimization should kick in)
        unchanged_reads = [call for call in file_reads if "unchanged.py" in call[1]]

        assert len(unchanged_reads) == 0, (
            f"BUG: Blob reuse optimization broken! File 'unchanged.py' was accessed {len(unchanged_reads)} times "
            f"even though it's unchanged in project git. The mtime+size optimization should reuse blob without reading.\n"
            f"File access calls: {unchanged_reads}"
        )


def test_blob_reuse_reads_file_for_size_collision():
    """Test that files with same size but different content are properly detected (reads file)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        # Create a main git repo
        subprocess.run(
            ["git", "init"], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Create .gitignore
        gitignore = project_root / ".gitignore"
        gitignore.write_text(".agentsmithy/\n")

        # Create file with version 1 and commit
        file_path = project_root / "code.py"
        v1 = "x = 1234567"  # 11 chars
        file_path.write_text(v1)

        # Create dialog after git init
        dialog_id = project.create_dialog(title="Test Dialog")

        subprocess.run(
            ["git", "add", "."], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Version 1"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Change file to v2 with SAME SIZE but different content
        v2 = "y = 7654321"  # 11 chars (same size!)
        file_path.write_text(v2)

        tracker = VersioningTracker(str(project_root), dialog_id)

        # Track file access (both read_bytes and open for streaming)
        original_read_bytes = Path.read_bytes
        original_open = open
        file_reads = []

        def tracked_read_bytes(self):
            file_reads.append(("read_bytes", str(self)))
            return original_read_bytes(self)

        def tracked_open(file_path_arg, *args, **kwargs):
            file_reads.append(("open", str(file_path_arg)))
            return original_open(file_path_arg, *args, **kwargs)

        # Create checkpoint with tracked file access
        with patch.object(Path, "read_bytes", tracked_read_bytes):
            with patch("builtins.open", tracked_open):
                _ = tracker.create_checkpoint("Checkpoint with changed file")

        # Verify: code.py SHOULD be accessed (size matches but content changed)
        code_reads = [call for call in file_reads if "code.py" in call[1]]

        assert len(code_reads) > 0, (
            "BUG: Size collision not detected! File 'code.py' was NOT read even though "
            "it has same size but different content than project git HEAD. "
            "This would cause corrupted checkpoint with old content."
        )

        # Verify checkpoint has correct (new) content
        repo = tracker.ensure_repo()
        session_ref = tracker._get_session_ref("session_1")
        session_head = repo.refs[session_ref]
        commit = repo[session_head]
        tree = repo[commit.tree]

        for name, _mode, sha in tree.items():
            if name == b"code.py":
                blob = repo[sha]
                assert (
                    blob.data.decode() == v2
                ), f"Checkpoint should have new content (v2), got: {blob.data.decode()}"
                return

        raise AssertionError("code.py not found in checkpoint")


def test_blob_reuse_optimization_with_multiple_files():
    """Test blob reuse with mix of unchanged and changed files.

    Verifies that:
    - Unchanged files are NOT read (optimization works)
    - Changed files ARE read (correctness maintained)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        # Create a main git repo
        subprocess.run(
            ["git", "init"], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Create .gitignore to exclude .agentsmithy
        gitignore = project_root / ".gitignore"
        gitignore.write_text(".agentsmithy/\n")

        # Create 3 files
        unchanged1 = project_root / "unchanged1.txt"
        unchanged1.write_text("This stays the same")

        unchanged2 = project_root / "unchanged2.txt"
        unchanged2.write_text("This also stays")

        changed = project_root / "changed.txt"
        changed.write_text("Original content")

        # Create dialog after git init
        dialog_id = project.create_dialog(title="Test Dialog")

        subprocess.run(
            ["git", "add", "."], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        # Wait for mtime optimization
        import time

        time.sleep(1.1)

        # Change only one file
        changed.write_text("Modified content!!")  # Different size

        tracker = VersioningTracker(str(project_root), dialog_id)

        # Track which files are accessed
        original_read_bytes = Path.read_bytes
        original_open = open
        file_reads = []

        def tracked_read_bytes(self):
            file_reads.append(("read_bytes", str(self)))
            return original_read_bytes(self)

        def tracked_open(file_path_arg, *args, **kwargs):
            file_reads.append(("open", str(file_path_arg)))
            return original_open(file_path_arg, *args, **kwargs)

        with patch.object(Path, "read_bytes", tracked_read_bytes):
            with patch("builtins.open", tracked_open):
                _ = tracker.create_checkpoint("Checkpoint")

        # Verify: unchanged files should NOT be accessed
        unchanged1_reads = [c for c in file_reads if "unchanged1.txt" in c[1]]
        unchanged2_reads = [c for c in file_reads if "unchanged2.txt" in c[1]]
        changed_reads = [c for c in file_reads if "changed.txt" in c[1]]

        assert len(unchanged1_reads) == 0, (
            f"BUG: unchanged1.txt was read {len(unchanged1_reads)} times even though unchanged! "
            f"Optimization broken."
        )
        assert len(unchanged2_reads) == 0, (
            f"BUG: unchanged2.txt was read {len(unchanged2_reads)} times even though unchanged! "
            f"Optimization broken."
        )
        assert (
            len(changed_reads) > 0
        ), "changed.txt should be read because it was modified"
