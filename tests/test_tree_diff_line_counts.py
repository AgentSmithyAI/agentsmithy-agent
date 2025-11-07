"""
Test for get_tree_diff line counting (additions/deletions).

This test verifies that get_tree_diff correctly counts lines for:
- Added files (should show additions > 0, deletions = 0)
- Deleted files (should show additions = 0, deletions > 0)
- Modified files (should show correct additions and deletions)

This is a regression test for a bug where deleted files would show deletions=0
because _count_lines returns (lines, 0) but the code was using the second value.
"""

import tempfile
from pathlib import Path

from agentsmithy.services.versioning import VersioningTracker


def test_tree_diff_counts_added_file_lines():
    """Test that added files show correct line count as additions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()

        tracker = VersioningTracker(str(project_root), "test_dialog")
        repo = tracker.ensure_repo()

        # Create initial empty commit on main
        dummy = project_root / "README.md"
        dummy.write_text("Initial\n")
        tracker.stage_file("README.md")
        cp1 = tracker.create_checkpoint("Initial commit")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Add a new file with 5 lines
        new_file = project_root / "new_file.py"
        new_file.write_text(
            """def func1():
    pass

def func2():
    pass
"""
        )
        tracker.stage_file("new_file.py")
        cp2 = tracker.create_checkpoint("Add new file")

        # Get diff between main and session_1
        diff = tracker.get_tree_diff("main", "session_1", include_diff=True)

        # Find new_file.py in diff
        new_files = [f for f in diff if "new_file.py" in f["path"]]
        assert len(new_files) == 1, f"Expected 1 new file, got {len(new_files)}"

        file_info = new_files[0]
        assert file_info["status"] == "added"
        assert file_info["additions"] == 5, (
            f"Expected 5 additions for new file, got {file_info['additions']}"
        )
        assert file_info["deletions"] == 0, (
            f"Expected 0 deletions for new file, got {file_info['deletions']}"
        )


def test_tree_diff_counts_deleted_file_lines():
    """Test that deleted files show correct line count as deletions.

    This is the BUG FIX test: _count_lines returns (lines, 0), but the code
    in get_tree_diff was using the second value (deletions) which is always 0.
    Should use the first value (lines/additions) for deleted file line count.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()

        tracker = VersioningTracker(str(project_root), "test_dialog")
        repo = tracker.ensure_repo()

        # Create initial commit with a file
        old_file = project_root / "old_file.py"
        old_file.write_text(
            """class OldClass:
    def method1(self):
        return 1

    def method2(self):
        return 2

    def method3(self):
        return 3
"""
        )
        tracker.stage_file("old_file.py")
        cp1 = tracker.create_checkpoint("Initial with old file")
        
        # Set main to cp1 (simulate approval)
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()
        
        # Delete the file and create new checkpoint (automatically on session_1)
        old_file.unlink()
        tracker.stage_file_deletion("old_file.py")
        cp2 = tracker.create_checkpoint("Delete old file")

        # Get diff between main and session_1
        diff = tracker.get_tree_diff("main", "session_1", include_diff=True)

        # Find old_file.py in diff
        deleted_files = [f for f in diff if "old_file.py" in f["path"]]
        assert len(deleted_files) == 1, f"Expected 1 deleted file, got {len(deleted_files)}"

        file_info = deleted_files[0]
        assert file_info["status"] == "deleted"
        assert file_info["additions"] == 0, (
            f"Expected 0 additions for deleted file, got {file_info['additions']}"
        )
        # THE BUG: This was showing 0 instead of 9
        assert file_info["deletions"] == 9, (
            f"BUG: Expected 9 deletions for deleted file (9 lines), got {file_info['deletions']}. "
            f"This means _count_lines return value is being used incorrectly."
        )


def test_tree_diff_counts_modified_file_lines():
    """Test that modified files show correct additions and deletions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()

        tracker = VersioningTracker(str(project_root), "test_dialog")
        repo = tracker.ensure_repo()

        # Create initial file
        test_file = project_root / "config.py"
        test_file.write_text(
            """# Config file
VERSION = "1.0"
DEBUG = False
"""
        )
        tracker.stage_file("config.py")
        cp1 = tracker.create_checkpoint("Initial config")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify the file
        test_file.write_text(
            """# Config file
VERSION = "2.0"
DEBUG = True
FEATURE_X = True
"""
        )
        tracker.stage_file("config.py")
        cp2 = tracker.create_checkpoint("Update config")

        # Get diff between main and session_1
        diff = tracker.get_tree_diff("main", "session_1", include_diff=True)

        # Find config.py in diff
        modified_files = [f for f in diff if "config.py" in f["path"]]
        assert len(modified_files) == 1, f"Expected 1 modified file, got {len(modified_files)}"

        file_info = modified_files[0]
        assert file_info["status"] == "modified"
        # Changed: VERSION line, DEBUG line, added FEATURE_X line
        # Should be 3 additions (changed lines + new line), 2 deletions (old lines)
        assert file_info["additions"] == 3, (
            f"Expected 3 additions, got {file_info['additions']}"
        )
        assert file_info["deletions"] == 2, (
            f"Expected 2 deletions, got {file_info['deletions']}"
        )
        assert file_info["diff"] is not None
        assert 'VERSION = "2.0"' in file_info["diff"]


def test_tree_diff_all_operations_together():
    """Comprehensive test with add, modify, and delete in one diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()

        tracker = VersioningTracker(str(project_root), "test_dialog")
        repo = tracker.ensure_repo()

        # Create initial state with 2 files
        file1 = project_root / "keep.txt"
        file1.write_text("Line 1\nLine 2\nLine 3\n")
        file2 = project_root / "delete.txt"
        file2.write_text("To be deleted\nSecond line\n")

        tracker.stage_file("keep.txt")
        tracker.stage_file("delete.txt")
        cp1 = tracker.create_checkpoint("Initial state")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # 1. Modify existing file
        file1.write_text("Line 1\nLine 2 modified\nLine 3\nLine 4 added\n")
        tracker.stage_file("keep.txt")

        # 2. Delete file
        file2.unlink()
        tracker.stage_file_deletion("delete.txt")

        # 3. Add new file
        file3 = project_root / "new.txt"
        file3.write_text("New line 1\nNew line 2\n")
        tracker.stage_file("new.txt")

        cp2 = tracker.create_checkpoint("Multiple changes")

        # Get diff
        diff = tracker.get_tree_diff("main", "session_1", include_diff=True)

        # Verify all three operations
        assert len(diff) == 3, f"Expected 3 changed files, got {len(diff)}"

        # Check modified file
        modified = [f for f in diff if f["path"] == "keep.txt"][0]
        assert modified["status"] == "modified"
        assert modified["additions"] == 2  # Line 2 changed + Line 4 added
        assert modified["deletions"] == 1  # Original Line 2

        # Check deleted file - THE BUG IS HERE
        deleted = [f for f in diff if f["path"] == "delete.txt"][0]
        assert deleted["status"] == "deleted"
        assert deleted["additions"] == 0
        assert deleted["deletions"] == 2, (
            f"BUG: Deleted file should show 2 deletions, got {deleted['deletions']}"
        )

        # Check added file
        added = [f for f in diff if f["path"] == "new.txt"][0]
        assert added["status"] == "added"
        assert added["additions"] == 2
        assert added["deletions"] == 0

