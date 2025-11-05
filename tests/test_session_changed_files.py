"""Tests for changed_files in /session endpoint."""

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


def test_session_changed_files_empty(client, temp_project):
    """Test changed_files is empty when no changes."""
    dialog_id = temp_project.create_dialog("test-1")

    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"] is False
    assert data["changed_files"] == []


def test_session_changed_files_added(client, temp_project):
    """Test changed_files shows added file with line count."""
    dialog_id = temp_project.create_dialog("test-1")

    # Create a new file
    new_file = temp_project.root / "new.txt"
    new_file.write_text("line1\nline2\nline3\n")

    # Create checkpoint (stages and commits the file)
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.stage_file("new.txt")
    tracker.create_checkpoint("Add new file")

    # Check session endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"] is True
    assert len(data["changed_files"]) == 1

    changed = data["changed_files"][0]
    assert changed["path"] == "new.txt"
    assert changed["status"] == "added"
    assert changed["additions"] == 3  # 3 lines
    assert changed["deletions"] == 0
    assert changed["diff"] is None  # No diff for added files


def test_session_changed_files_modified_with_diff(client, temp_project):
    """Test changed_files shows modified file with diff text."""
    dialog_id = temp_project.create_dialog("test-1")

    # Create initial file and approve it (creates main baseline)
    test_file = temp_project.root / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")

    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.stage_file("test.txt")
    tracker.create_checkpoint("Initial")

    # Manually approve to main without creating new session
    # (simulates the initial state)
    repo = tracker.ensure_repo()
    session_ref = b"refs/heads/session_1"
    main_ref = b"refs/heads/main"
    repo.refs[main_ref] = repo.refs[session_ref]

    # Modify the file in the same session
    test_file.write_text("line1\nmodified line2\nline3\nline4\n")
    tracker.stage_file("test.txt")
    tracker.create_checkpoint("Modify")

    # Check session endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"] is True
    assert len(data["changed_files"]) >= 1

    # Find the modified file
    modified = next((c for c in data["changed_files"] if c["path"] == "test.txt"), None)
    assert modified is not None
    assert modified["status"] == "modified"
    assert modified["additions"] > 0
    assert modified["deletions"] > 0

    # Check that diff is present and contains unified diff markers
    assert modified["diff"] is not None
    diff_text = modified["diff"]
    assert isinstance(diff_text, str)
    # Unified diff should contain +/- lines
    assert "+" in diff_text or "-" in diff_text


def test_session_changed_files_binary(client, temp_project):
    """Test changed_files handles binary files (no diff text)."""
    dialog_id = temp_project.create_dialog("test-1")

    # Create initial binary file
    binary_file = temp_project.root / "image.bin"
    binary_file.write_bytes(b"binary content\x00\x01\x02")

    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.stage_file("image.bin")
    tracker.create_checkpoint("Initial")

    # Manually approve to main
    repo = tracker.ensure_repo()
    session_ref = b"refs/heads/session_1"
    main_ref = b"refs/heads/main"
    repo.refs[main_ref] = repo.refs[session_ref]

    # Modify binary file
    binary_file.write_bytes(b"modified binary\x00\x03\x04")
    tracker.stage_file("image.bin")
    tracker.create_checkpoint("Modify binary")

    # Check session endpoint
    response = client.get(f"/api/dialogs/{dialog_id}/session")

    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"] is True
    assert len(data["changed_files"]) >= 1

    # Find the binary file
    binary = next((c for c in data["changed_files"] if c["path"] == "image.bin"), None)
    assert binary is not None
    assert binary["status"] == "modified"
    assert binary["additions"] == 0  # Binary files show 0
    assert binary["deletions"] == 0  # Binary files show 0
    assert binary["diff"] is None  # No diff for binary files
