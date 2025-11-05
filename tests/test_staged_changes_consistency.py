"""Test for staged changes consistency in /session endpoint.

This test reproduces the issue where has_unapproved=true but changed_files=[]
when there are staged (but not committed) changes.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.api.deps import get_project
from agentsmithy.core.project import set_workspace
from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        workspace = set_workspace(project_root)
        project = workspace.get_project("test")
        project.ensure_state_dir()
        project.ensure_dialogs_dir()
        yield project


@pytest.fixture
def client(temp_project):
    """Create test client with project dependency override."""
    app = create_app()

    # Override get_project dependency
    def override_get_project():
        return temp_project

    app.dependency_overrides[get_project] = override_get_project

    return TestClient(app)


def test_staged_changes_without_commit_shows_empty_changed_files(client, temp_project):
    """
    Reproduce issue: staged changes cause has_unapproved=true but changed_files=[].

    Scenario:
    1. Create a new file
    2. Stage it (tracker.stage_file())
    3. DON'T create checkpoint (no commit)
    4. Call /session endpoint

    Expected behavior:
    - has_unapproved should be True (because there are staged changes)
    - changed_files should NOT be empty (should show what's staged)

    Current broken behavior:
    - has_unapproved = True ✓
    - changed_files = [] ✗ (inconsistent!)
    """
    dialog_id = temp_project.create_dialog("test-staged")

    # Create a new file
    new_file = temp_project.root / "staged.txt"
    new_file.write_text("This file is staged but not committed\n")

    # Stage the file (add to git index) but DON'T commit
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.stage_file("staged.txt")
    # NOTE: We are NOT calling tracker.create_checkpoint() here!

    # Call /session endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()

    # This should be True (and it is)
    assert data["has_unapproved"] is True, "Should detect staged changes"

    # This is the bug: changed_files is empty!
    # User sees has_unapproved=true but doesn't see what files changed
    print(f"has_unapproved: {data['has_unapproved']}")
    print(f"changed_files: {data['changed_files']}")

    # This assertion will FAIL with current implementation
    assert len(data["changed_files"]) > 0, (
        "BUG: changed_files is empty even though has_unapproved=True! "
        "User can't see what files are staged."
    )
    assert data["changed_files"][0]["path"] == "staged.txt"
    assert data["changed_files"][0]["status"] == "added"


def test_staged_and_committed_changes_both_shown(client, temp_project):
    """
    Test that both staged AND committed changes are shown.

    Scenario:
    1. Create file1.txt, stage and commit
    2. Approve (moves to main)
    3. Create file2.txt, stage and commit
    4. Create file3.txt, stage but DON'T commit
    5. Call /session endpoint

    Expected: changed_files should show BOTH file2.txt and file3.txt
    """
    dialog_id = temp_project.create_dialog("test-both")

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Step 1-2: Initial file and approve
    file1 = temp_project.root / "file1.txt"
    file1.write_text("initial\n")
    tracker.stage_file("file1.txt")
    tracker.create_checkpoint("Initial")

    # Manually approve to main
    repo = tracker.ensure_repo()
    session_ref = b"refs/heads/session_1"
    main_ref = b"refs/heads/main"
    repo.refs[main_ref] = repo.refs[session_ref]

    # Step 3: Create and commit file2
    file2 = temp_project.root / "file2.txt"
    file2.write_text("committed\n")
    tracker.stage_file("file2.txt")
    tracker.create_checkpoint("Add file2")

    # Step 4: Create and stage (but not commit) file3
    file3 = temp_project.root / "file3.txt"
    file3.write_text("staged only\n")
    tracker.stage_file("file3.txt")
    # NOT calling create_checkpoint() for file3!

    # Step 5: Check /session endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()

    assert data["has_unapproved"] is True

    # Should show BOTH committed and staged files
    paths = {f["path"] for f in data["changed_files"]}

    # file2.txt is committed (should be shown)
    assert "file2.txt" in paths, "Committed file should be in changed_files"

    # file3.txt is only staged (currently NOT shown - this is the bug)
    assert "file3.txt" in paths, "Staged-only file should be in changed_files"


def test_staged_and_committed_same_file_no_duplicates(client, temp_project):
    """
    Test that a file that is both committed AND staged doesn't appear twice.

    Scenario:
    1. Create file.txt, stage and commit (first version)
    2. Approve
    3. Modify file.txt, stage and commit (second version)
    4. Modify file.txt again, stage but DON'T commit (third version, staged only)
    5. Call /session endpoint

    Expected: file.txt should appear ONCE in changed_files (not twice)
    """
    dialog_id = temp_project.create_dialog("test-dedup")

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Step 1-2: Initial version and approve
    test_file = temp_project.root / "file.txt"
    test_file.write_text("version 1\n")
    tracker.stage_file("file.txt")
    tracker.create_checkpoint("Version 1")

    repo = tracker.ensure_repo()
    session_ref = b"refs/heads/session_1"
    main_ref = b"refs/heads/main"
    repo.refs[main_ref] = repo.refs[session_ref]

    # Step 3: Second version (committed)
    test_file.write_text("version 2\n")
    tracker.stage_file("file.txt")
    tracker.create_checkpoint("Version 2")

    # Step 4: Third version (staged only)
    test_file.write_text("version 3\n")
    tracker.stage_file("file.txt")

    # Step 5: Check endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"] is True

    # Count how many times file.txt appears
    file_txt_count = sum(1 for f in data["changed_files"] if f["path"] == "file.txt")

    # Should appear ONCE (not twice) - deduplication should work
    assert (
        file_txt_count == 1
    ), f"file.txt appears {file_txt_count} times, expected 1 (deduplication failed)"

    # Verify the file info
    file_info = next(f for f in data["changed_files"] if f["path"] == "file.txt")
    assert file_info["status"] == "modified"
