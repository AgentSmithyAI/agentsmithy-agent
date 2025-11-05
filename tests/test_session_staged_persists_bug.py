"""
Test for bug: session endpoint returns additions=0 when file remains in staging area after commit.

Root cause:
- By design, staging area persists after create_checkpoint() (see versioning.py comments)
- Session endpoint checks staged files FIRST and adds with additions=0
- Then checks committed but SKIPS files already in list (deduplication)
- Result: Committed files with real diff show as additions=0

This is the REAL bug from user's report!
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


def test_session_bug_file_in_staging_after_commit():
    """
    EXACT reproduction of the bug user reported.

    Scenario:
    1. File is staged and committed
    2. Staging area is NOT cleared (by design)
    3. has_staged_changes() returns True
    4. Session endpoint adds file with additions=0 (staged version)
    5. Then skips file when processing committed changes (already in list)
    6. User sees additions=0 instead of real diff

    Expected: Committed version should OVERRIDE staged version!
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
        css_file = project_root / "media" / "chat.css"
        css_file.parent.mkdir(parents=True, exist_ok=True)
        css_file.write_text(
            """body { margin: 0; }
.session-actions { display: flex; }
"""
        )

        tracker.stage_file(str(css_file))
        cp1 = tracker.create_checkpoint("Initial")
        repo.refs[b"refs/heads/main"] = cp1.commit_id.encode()

        # Modify and commit file
        css_file.write_text(
            """body { margin: 0; }

/* New styles */
.session-changes { padding: 10px; }
.session-changes-header { font-size: 12px; }

.session-actions { display: flex; }
"""
        )

        tracker.stage_file(str(css_file))
        _ = tracker.create_checkpoint("Add session changes styles")

        # CRITICAL: Now modify file AGAIN and re-stage (without committing)
        # This simulates the real scenario where file has both committed and staged changes
        css_file.write_text(
            """body { margin: 0; }

/* New styles */
.session-changes { padding: 10px; }
.session-changes-header { font-size: 12px; }
/* Additional staged changes */
.session-change-item { display: flex; }

.session-actions { display: flex; }
"""
        )
        tracker.stage_file(str(css_file))
        # DON'T create checkpoint - leave these changes in staging only

        # Now file has:
        # - Committed changes: main -> session_1 (should show additions>0)
        # - Additional staged changes: session_1 HEAD -> index (not committed)

        assert tracker.has_staged_changes() is True

        staged = tracker.get_staged_files("session_1")
        staged_paths = [f["path"] for f in staged]
        assert "media/chat.css" in staged_paths or any(
            "chat.css" in p for p in staged_paths
        ), f"File should be in staging area after re-staging. Staged: {staged_paths}"

        # Now call session endpoint
        app = create_app()

        def mock_get_project():
            return project

        from agentsmithy.api import deps

        app.dependency_overrides[deps.get_project] = mock_get_project
        client = TestClient(app)

        response = client.get(f"/api/dialogs/{dialog_id}/session")
        assert response.status_code == 200
        data = response.json()

        print(f"\nResponse: {data}")

        # Find CSS file in response
        css_files = [f for f in data["changed_files"] if "chat.css" in f["path"]]

        # Should have at least one (may have duplicates due to another bug)
        assert (
            len(css_files) > 0
        ), f"CSS file not found in changed_files: {data['changed_files']}"

        # Check if ANY of the entries has additions=0 (the bug)
        zero_additions_entries = [f for f in css_files if f["additions"] == 0]

        if zero_additions_entries:
            print("\nBUG REPRODUCED!")
            print(f"File with additions=0: {zero_additions_entries}")
            print(f"All CSS entries: {css_files}")

            pytest.fail(
                f"BUG: File shows additions=0 even though it's committed with real changes!\n"
                f"Root cause: File is in staging area after commit, endpoint adds staged version first,\n"
                f"then skips committed version due to deduplication logic.\n"
                f"CSS entries: {css_files}"
            )

        # All entries should have additions > 0
        for css_file in css_files:
            assert (
                css_file["additions"] > 0
            ), f"File should have additions>0, got {css_file['additions']}"
            assert css_file["diff"] is not None, "File should have diff"


def test_session_deduplication_should_prefer_committed():
    """
    Test the correct behavior: when file is in both staged and committed,
    prefer committed version (with real diff).
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
        file1.write_text("initial\nmodified line 2\nmodified line 3\n")
        tracker.stage_file(str(file1))
        _ = tracker.create_checkpoint("Modify file1")

        # Verify staging persists
        assert tracker.has_staged_changes() is True

        # Create file2 (staged only, NO commit)
        file2 = project_root / "file2.txt"
        file2.write_text("new file\n")
        tracker.stage_file(str(file2))

        # Call session endpoint
        app = create_app()

        def mock_get_project():
            return project

        from agentsmithy.api import deps

        app.dependency_overrides[deps.get_project] = mock_get_project
        client = TestClient(app)

        response = client.get(f"/api/dialogs/{dialog_id}/session")
        assert response.status_code == 200
        data = response.json()

        # Group files by path (handle duplicates)
        from collections import defaultdict

        files_by_path = defaultdict(list)
        for f in data["changed_files"]:
            # Normalize path (remove absolute prefix)
            path = f["path"]
            if "file1.txt" in path:
                files_by_path["file1.txt"].append(f)
            elif "file2.txt" in path:
                files_by_path["file2.txt"].append(f)

        print(f"\nFiles by path: {dict(files_by_path)}")

        # file1: committed -> ALL entries should have additions>0
        file1_entries = files_by_path.get("file1.txt", [])
        assert len(file1_entries) > 0, "file1 should be in changed_files"

        for entry in file1_entries:
            assert entry["additions"] > 0, (
                f"BUG: file1 is committed but entry shows additions={entry['additions']}. "
                f"All entries for committed files should have real diff! Entry: {entry}"
            )
            assert (
                entry["diff"] is not None
            ), f"Committed file should have diff. Entry: {entry}"

        # file2: staged only -> entries should have additions=0
        file2_entries = files_by_path.get("file2.txt", [])
        assert len(file2_entries) > 0, "file2 should be in changed_files"

        for entry in file2_entries:
            assert (
                entry["additions"] == 0
            ), f"file2 is staged-only, should have additions=0, got {entry['additions']}"
            assert entry["diff"] is None, "Staged-only file should not have diff"
