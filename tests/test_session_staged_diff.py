"""
Test that staged files show real diff information (not just additions=0).

This is a fix for the issue where staged-only files would show additions=0, deletions=0, diff=null,
even though they contain real changes from HEAD.
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


def test_staged_files_show_real_diff():
    """
    Test that staged (but not yet committed) files show real additions/deletions/diff.

    Scenario:
    1. Commit file1 to create baseline
    2. Approve to move to new session
    3. Modify and STAGE file1 (but don't commit)
    4. Session endpoint should show real diff, not additions=0

    This was the bug: when main == session_N (same tree), staged files would show as additions=0.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        dialog_id = project.create_dialog(title="Test", set_current=True)

        tracker = VersioningTracker(str(project_root), dialog_id)
        repo = tracker.ensure_repo()

        # Create and commit initial file
        test_file = project_root / "app.py"
        test_file.write_text(
            """def hello():
    print("Hello")
"""
        )

        tracker.stage_file(str(test_file))
        cp1 = tracker.create_checkpoint("Initial version")

        # Approve to main (simulate approval)
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Now modify file and STAGE (but don't commit)
        test_file.write_text(
            """def hello():
    print("Hello")

def goodbye():
    print("Goodbye")
"""
        )

        tracker.stage_file(str(test_file))
        # DON'T create checkpoint - leave it staged only

        # At this point:
        # - main tree == session_1 tree (same commit)
        # - But file is staged with changes
        # - Should show real diff!

        # Setup API
        app = create_app()

        def mock_get_project():
            return project

        from agentsmithy.api import deps

        app.dependency_overrides[deps.get_project] = mock_get_project
        client = TestClient(app)

        # Call session endpoint
        response = client.get(f"/api/dialogs/{dialog_id}/session")
        assert response.status_code == 200
        data = response.json()

        assert data["has_unapproved"] is True

        # Find our file
        files = [f for f in data["changed_files"] if "app.py" in f["path"]]
        assert len(files) == 1, f"Expected 1 file, got {len(files)}: {files}"

        file_info = files[0]

        # THE FIX: Staged files should show REAL diff, not zeros!
        print(f"\nStaged file info: {file_info}")

        assert file_info["additions"] > 0, (
            f"BUG: Staged file shows additions=0!\n"
            f"Staged files should show real diff between HEAD and staging area.\n"
            f"File info: {file_info}"
        )

        assert file_info["diff"] is not None, "Staged file should have diff"
        assert (
            "+def goodbye():" in file_info["diff"]
        ), "Diff should contain added function"


def test_staged_modified_file_has_correct_diff():
    """
    Test the actual diff content for staged modified files.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        dialog_id = project.create_dialog(title="Test", set_current=True)

        tracker = VersioningTracker(str(project_root), dialog_id)
        repo = tracker.ensure_repo()

        # Create initial file
        test_file = project_root / "config.json"
        test_file.write_text('{"version": "1.0"}\n')

        tracker.stage_file("config.json")
        cp1 = tracker.create_checkpoint("Initial config")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify and stage (no commit)
        test_file.write_text('{"version": "2.0", "debug": true}\n')
        tracker.stage_file("config.json")

        # Setup API
        app = create_app()

        def mock_get_project():
            return project

        from agentsmithy.api import deps

        app.dependency_overrides[deps.get_project] = mock_get_project
        client = TestClient(app)

        response = client.get(f"/api/dialogs/{dialog_id}/session")
        assert response.status_code == 200
        data = response.json()

        files = [f for f in data["changed_files"] if "config.json" in f["path"]]
        assert len(files) == 1

        file_info = files[0]

        # Check diff details
        assert (
            file_info["additions"] == 1
        ), f"Expected 1 addition, got {file_info['additions']}"
        assert (
            file_info["deletions"] == 1
        ), f"Expected 1 deletion, got {file_info['deletions']}"
        assert file_info["diff"] is not None
        assert (
            '-{"version": "1.0"}' in file_info["diff"]
        ), "Diff should show removed line"
        assert (
            '+{"version": "2.0", "debug": true}' in file_info["diff"]
        ), "Diff should show added line"


def test_staged_added_file_shows_line_count():
    """
    Test that newly added (staged) files show correct line count as additions.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        dialog_id = project.create_dialog(title="Test", set_current=True)

        tracker = VersioningTracker(str(project_root), dialog_id)
        repo = tracker.ensure_repo()

        # Create empty baseline
        dummy = project_root / "dummy.txt"
        dummy.write_text("dummy\n")
        tracker.stage_file("dummy.txt")
        cp1 = tracker.create_checkpoint("Initial")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Add new file (staged only)
        new_file = project_root / "new_module.py"
        new_file.write_text(
            """class MyClass:
    def method1(self):
        pass

    def method2(self):
        pass
"""
        )
        tracker.stage_file("new_module.py")

        # Setup API
        app = create_app()

        def mock_get_project():
            return project

        from agentsmithy.api import deps

        app.dependency_overrides[deps.get_project] = mock_get_project
        client = TestClient(app)

        response = client.get(f"/api/dialogs/{dialog_id}/session")
        assert response.status_code == 200
        data = response.json()

        files = [f for f in data["changed_files"] if "new_module.py" in f["path"]]
        assert len(files) == 1

        file_info = files[0]

        assert file_info["status"] == "added"
        assert (
            file_info["additions"] == 6
        ), f"Expected 6 lines, got {file_info['additions']}"
        assert file_info["deletions"] == 0
        # For added files, diff is None (we don't show full content)
        assert file_info["diff"] is None
