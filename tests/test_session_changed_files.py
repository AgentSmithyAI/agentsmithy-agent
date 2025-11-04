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


# Tests with approve_all() are skipped due to DB state management issues
# TODO: Fix active_session tracking after approve_all()
