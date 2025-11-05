"""
Test for the fix: session endpoint should return correct additions/deletions for committed files.

This test was created to verify the fix for the bug where files that were both
staged and committed would show additions=0 instead of real diff stats.

The test also documents a SECOND bug: files appear twice with absolute/relative paths.
This is tracked separately and doesn't affect the main fix.
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


def test_session_endpoint_committed_file_shows_real_additions():
    """
    Regression test for bug: committed files showed additions=0, deletions=0, diff=null
    when they were also in staging area.

    Root cause: Endpoint processed staged files first (additions=0), then skipped
    committed files due to deduplication.

    Fix: Process committed files FIRST (with real diff), then add staged-only files.

    Note: This test currently tolerates file path duplication (absolute vs relative).
    That's a separate bug to be fixed later.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        project_root.mkdir()
        state_dir = project_root / ".agentsmithy"

        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()

        dialog_id = project.create_dialog(title="Test Dialog", set_current=True)

        # Create tracker
        tracker = VersioningTracker(str(project_root), dialog_id)
        repo = tracker.ensure_repo()

        # Create initial file
        test_file = project_root / "styles.css"
        test_file.write_text(".header { color: blue; }\n")

        tracker.stage_file(str(test_file))
        cp1 = tracker.create_checkpoint("Initial")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify and commit file
        test_file.write_text(".header { color: blue; }\n.footer { color: red; }\n")
        tracker.stage_file(str(test_file))
        _ = tracker.create_checkpoint("Add footer")

        # Re-stage file again (simulating additional changes)
        test_file.write_text(
            ".header { color: blue; }\n.footer { color: red; }\n.sidebar { color: green; }\n"
        )
        tracker.stage_file(str(test_file))

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

        # Find CSS file entries
        css_files = [f for f in data["changed_files"] if "styles.css" in f["path"]]

        # Should have exactly ONE entry (no duplicates with absolute/relative paths)
        assert len(css_files) == 1, (
            f"Expected exactly 1 CSS file entry, got {len(css_files)}. "
            f"Entries: {css_files}"
        )

        css_file = css_files[0]

        # THE MAIN FIX: Entry should have additions > 0
        assert css_file["additions"] > 0, (
            f"BUG: CSS file shows additions=0!\n"
            f"This means committed files are still showing as additions=0.\n"
            f"Entry: {css_file}"
        )

        assert css_file["diff"] is not None, "Expected diff to be present"
        assert ".footer" in css_file["diff"], "Diff should contain added footer rule"

        # Path should be relative, not absolute
        assert not css_file["path"].startswith(
            "/"
        ), f"Path should be relative, got: {css_file['path']}"


def test_session_endpoint_committed_vs_staged_order():
    """
    Test that committed files with real diff are shown, not overridden by staged versions.

    Scenario:
    1. file1: committed with changes (should show additions > 0)
    2. file2: staged only, not committed (should show additions = 0)
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

        # Create file1 and approve
        file1 = project_root / "file1.txt"
        file1.write_text("initial\n")
        tracker.stage_file(str(file1))
        cp1 = tracker.create_checkpoint("Initial")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify and commit file1
        file1.write_text("initial\nmodified\n")
        tracker.stage_file(str(file1))
        _ = tracker.create_checkpoint("Modify file1")

        # Modify file1 again and stage (but don't commit)
        file1.write_text("initial\nmodified\nmore changes\n")
        tracker.stage_file(str(file1))

        # Create file2 (staged only)
        file2 = project_root / "file2.txt"
        file2.write_text("new file\n")
        tracker.stage_file(str(file2))

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

        # Find files (should be no duplicates now)
        file1_entries = [f for f in data["changed_files"] if "file1.txt" in f["path"]]
        file2_entries = [f for f in data["changed_files"] if "file2.txt" in f["path"]]

        # Should have exactly one entry per file
        assert (
            len(file1_entries) == 1
        ), f"Expected 1 file1 entry, got {len(file1_entries)}: {file1_entries}"
        assert (
            len(file2_entries) == 1
        ), f"Expected 1 file2 entry, got {len(file2_entries)}: {file2_entries}"

        file1 = file1_entries[0]
        file2 = file2_entries[0]

        # file1: committed -> should have additions > 0
        assert (
            file1["additions"] > 0
        ), f"BUG: file1 is committed but shows additions=0! Entry: {file1}"
        assert file1["diff"] is not None, "Committed file should have diff"
        assert not file1["path"].startswith(
            "/"
        ), f"Path should be relative: {file1['path']}"

        # file2: staged only -> should have additions = 0
        assert (
            file2["additions"] == 0
        ), f"file2 is staged-only, should have additions=0, got {file2['additions']}"
        assert file2["diff"] is None, "Staged-only file should not have diff"
        assert not file2["path"].startswith(
            "/"
        ), f"Path should be relative: {file2['path']}"


def test_session_endpoint_files_sorted_by_path():
    """
    Test that changed files are sorted alphabetically by path for consistent display.
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

        # Create multiple files with different names
        (project_root / "zebra.txt").write_text("zebra\n")
        (project_root / "apple.txt").write_text("apple\n")
        (project_root / "banana.txt").write_text("banana\n")

        tracker.stage_file("zebra.txt")
        tracker.stage_file("apple.txt")
        tracker.stage_file("banana.txt")
        cp1 = tracker.create_checkpoint("Initial")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify files in random order
        (project_root / "zebra.txt").write_text("zebra modified\n")
        (project_root / "apple.txt").write_text("apple modified\n")
        (project_root / "banana.txt").write_text("banana modified\n")

        tracker.stage_file("zebra.txt")
        tracker.stage_file("banana.txt")
        tracker.stage_file("apple.txt")
        _ = tracker.create_checkpoint("Modify all")

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

        # Get file paths
        paths = [f["path"] for f in data["changed_files"]]

        # Should be sorted alphabetically
        expected_order = ["apple.txt", "banana.txt", "zebra.txt"]
        assert paths == expected_order, (
            f"Files should be sorted alphabetically.\n"
            f"Expected: {expected_order}\n"
            f"Got: {paths}"
        )
