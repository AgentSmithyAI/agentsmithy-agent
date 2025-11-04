"""Test that reset creates auto-save checkpoint before discarding changes.

Tests the safety feature where reset_to_approved() creates an automatic checkpoint
if there are uncommitted or staged changes, so work is never lost.
"""

import pytest
from fastapi.testclient import TestClient

from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def client(temp_project):
    """Create test client with project dependency override."""
    from agentsmithy.api.app import create_app
    from agentsmithy.api.deps import get_project

    app = create_app()
    app.dependency_overrides[get_project] = lambda: temp_project
    return TestClient(app)


def test_reset_creates_auto_checkpoint_for_uncommitted_changes(temp_project):
    """Test that reset creates auto-checkpoint when there are uncommitted changes."""
    # Create dialog
    dialog_id = temp_project.create_dialog(
        title="Test Reset Auto-Checkpoint", set_current=True
    )

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Create and approve initial checkpoint
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Approved content")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all()

    # Make changes in new session
    test_file.write_text("Unapproved content")
    tracker.create_checkpoint("Checkpoint 2")

    # Reset to approved - should create auto-checkpoint
    result = tracker.reset_to_approved()

    # Verify auto-checkpoint was created
    assert "pre_reset_checkpoint" in result
    assert result["pre_reset_checkpoint"] is not None

    # Verify we can restore to the auto-checkpoint
    tracker.restore_checkpoint(result["pre_reset_checkpoint"])

    # File should have unapproved content again
    assert test_file.read_text() == "Unapproved content"


def test_reset_creates_auto_checkpoint_for_staged_changes(temp_project):
    """Test that reset creates auto-checkpoint when there are staged changes."""
    # Create dialog
    dialog_id = temp_project.create_dialog(
        title="Test Reset Staged Auto-Checkpoint", set_current=True
    )

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Create and approve initial checkpoint
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Approved content")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all()

    # Stage a file without creating checkpoint
    staged_file = temp_project.root / "staged.txt"
    staged_file.write_text("Staged content")
    tracker.stage_file("staged.txt")

    # Reset to approved - should create auto-checkpoint
    result = tracker.reset_to_approved()

    # Verify auto-checkpoint was created
    assert "pre_reset_checkpoint" in result
    assert result["pre_reset_checkpoint"] is not None

    # Verify we can restore to the auto-checkpoint
    tracker.restore_checkpoint(result["pre_reset_checkpoint"])

    # Staged file should be restored
    assert staged_file.exists()
    assert staged_file.read_text() == "Staged content"


def test_reset_no_auto_checkpoint_when_clean(temp_project):
    """Test that reset does NOT create auto-checkpoint when there are no changes."""
    # Create dialog
    dialog_id = temp_project.create_dialog(
        title="Test Reset No Auto-Checkpoint", set_current=True
    )

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Create and approve initial checkpoint
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Approved content")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all()

    # Reset without making any changes
    result = tracker.reset_to_approved()

    # Verify NO auto-checkpoint was created (no changes to save)
    assert result.get("pre_reset_checkpoint") is None


def test_session_endpoint_after_reset_with_auto_checkpoint(client, temp_project):
    """Test that session endpoint shows no unapproved changes after reset.

    This is the main regression test: even if there were uncommitted/staged
    changes before reset (which triggered auto-checkpoint), the session endpoint
    should show has_unapproved=false after reset.
    """
    # Create dialog
    dialog_id = temp_project.create_dialog(
        title="Test Session After Reset With Auto", set_current=True
    )

    tracker = VersioningTracker(str(temp_project.root), dialog_id)

    # Create and approve initial checkpoint
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Approved")
    tracker.create_checkpoint("Checkpoint 1")
    tracker.approve_all()

    # Make changes in new session
    test_file.write_text("Unapproved")
    tracker.create_checkpoint("Checkpoint 2")

    # Stage additional file
    staged_file = temp_project.root / "staged.txt"
    staged_file.write_text("Staged content")
    tracker.stage_file("staged.txt")

    # Verify session shows unapproved changes
    response = client.get(f"/api/dialogs/{dialog_id}/session")
    assert response.status_code == 200
    data = response.json()
    assert data["has_unapproved"], "Should have unapproved changes before reset"

    # Reset to approved (should create auto-checkpoint)
    reset_response = client.post(f"/api/dialogs/{dialog_id}/reset")
    assert reset_response.status_code == 200
    reset_data = reset_response.json()

    # Verify auto-checkpoint was created
    assert "pre_reset_checkpoint" in reset_data
    assert reset_data["pre_reset_checkpoint"] is not None

    # CRITICAL: Verify session endpoint now shows NO unapproved changes
    # Even though auto-checkpoint was created, it's in the old (abandoned) session
    # The new session should start clean from approved state
    response = client.get(f"/api/dialogs/{dialog_id}/session")
    assert response.status_code == 200
    data = response.json()
    assert not data["has_unapproved"], "Should have NO unapproved changes after reset"
    assert data["active_session"] is None, "Should have no active session after reset"
    assert data["session_ref"] is None, "Should have no session ref after reset"

    # Verify files were restored to approved state
    assert test_file.read_text() == "Approved"
    assert not staged_file.exists(), "Staged file should be deleted after reset"

    # Verify we can restore the auto-checkpoint directly using tracker
    # (auto-checkpoint is in the abandoned session but still accessible via git)
    tracker.restore_checkpoint(reset_data["pre_reset_checkpoint"])

    # After restore, files should have unapproved content again
    assert test_file.read_text() == "Unapproved"
    assert staged_file.exists(), "Staged file should be restored"
