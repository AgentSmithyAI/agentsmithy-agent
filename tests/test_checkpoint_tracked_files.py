"""Tests for checkpoint tracking of agent-modified files.

Verifies that:
1. Files modified by agent tools are tracked and deleted on restore
2. Files created by user manually are not deleted on restore
3. User files edited by agent are restored but not deleted
"""

import tempfile
from pathlib import Path

import pytest

from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker
from agentsmithy.tools.builtin.delete_file import DeleteFileTool
from agentsmithy.tools.builtin.replace_in_file import ReplaceInFileTool
from agentsmithy.tools.builtin.write_file import WriteFileTool


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        state_dir = project_root / ".agentsmithy"
        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()
        project.ensure_dialogs_dir()
        yield project


def test_agent_created_file_deleted_on_restore(temp_project):
    """Test that files created by agent are deleted when restoring to earlier checkpoint."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Create initial file
    initial_file = temp_project.root / "main.py"
    initial_file.write_text("# main")

    # Checkpoint 1: initial state
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("Initial state")

    # Agent creates new file via write_to_file tool
    tool = WriteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    result = asyncio.run(
        tool.arun(tool_input={"path": "agent_file.py", "content": "# created by agent"})
    )
    assert result["type"] == "write_file_result"

    # Verify file exists
    agent_file = temp_project.root / "agent_file.py"
    assert agent_file.exists()

    # Checkpoint 2: after agent created file
    tracker.create_checkpoint("Agent created file")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # Agent file should be deleted
    assert not agent_file.exists(), "Agent-created file should be deleted on restore"
    # Initial file should still exist
    assert initial_file.exists()


def test_user_created_file_preserved_on_restore(temp_project):
    """Test that files created by user manually are preserved when restoring."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Checkpoint 1: initial state
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("Initial state")

    # Agent creates a file
    tool = WriteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    asyncio.run(tool.arun(tool_input={"path": "agent.py", "content": "# agent"}))

    # Checkpoint 2
    tracker.create_checkpoint("Agent file")

    # User creates file manually (not via tool)
    user_file = temp_project.root / "user_config.yaml"
    user_file.write_text("user: data")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # Agent file should be deleted
    assert not (temp_project.root / "agent.py").exists()
    # User file should be preserved
    assert user_file.exists(), "User-created file should not be deleted on restore"


def test_user_file_edited_by_agent_restored_not_deleted(temp_project):
    """Test that when agent edits user's file, restore reverts changes but keeps file."""
    dialog_id = temp_project.create_dialog(title="Test")

    # User creates file manually
    user_file = temp_project.root / "config.py"
    user_file.write_text("VERSION = 1")

    # Checkpoint 1: includes user file (full snapshot)
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("User file exists")

    # Agent modifies user's file
    tool = ReplaceInFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    asyncio.run(
        tool.arun(
            tool_input={
                "path": "config.py",
                "diff": "-------- SEARCH\nVERSION = 1\n=======\nVERSION = 2  # updated\n+++++++ REPLACE\n",
            }
        )
    )

    # Verify changes applied
    assert "VERSION = 2" in user_file.read_text()

    # Checkpoint 2
    tracker.create_checkpoint("Agent edited user file")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # File should still exist
    assert user_file.exists(), "User file should not be deleted"
    # Changes should be reverted
    assert "VERSION = 1" in user_file.read_text()
    assert "VERSION = 2" not in user_file.read_text()


def test_multiple_agent_files_deleted_on_restore(temp_project):
    """Test that multiple agent-created files are all deleted on restore."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Checkpoint 1: empty
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("Empty")

    # Agent creates multiple files
    tool = WriteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    asyncio.run(tool.arun(tool_input={"path": "file1.py", "content": "# 1"}))
    asyncio.run(tool.arun(tool_input={"path": "file2.py", "content": "# 2"}))
    asyncio.run(tool.arun(tool_input={"path": "subdir/file3.py", "content": "# 3"}))

    # All files exist
    assert (temp_project.root / "file1.py").exists()
    assert (temp_project.root / "file2.py").exists()
    assert (temp_project.root / "subdir/file3.py").exists()

    # Checkpoint 2
    tracker.create_checkpoint("Agent created 3 files")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # All agent files should be deleted
    assert not (temp_project.root / "file1.py").exists()
    assert not (temp_project.root / "file2.py").exists()
    assert not (temp_project.root / "subdir/file3.py").exists()


def test_agent_deletes_file_then_restore(temp_project):
    """Test restore when agent deleted a file."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Create initial file
    victim = temp_project.root / "victim.py"
    victim.write_text("# to be deleted")

    # Checkpoint 1: file exists
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("File exists")

    # Agent deletes file
    tool = DeleteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    asyncio.run(tool.arun(tool_input={"path": "victim.py"}))

    # File deleted
    assert not victim.exists()

    # Checkpoint 2
    tracker.create_checkpoint("Agent deleted file")

    # Restore to checkpoint 1
    tracker.restore_checkpoint(cp1.commit_id)

    # File should be restored
    assert victim.exists()
    assert victim.read_text() == "# to be deleted"


def test_mixed_scenario_user_and_agent_files(temp_project):
    """Complex scenario: user and agent both create/edit files, then restore."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Initial state
    base_file = temp_project.root / "base.py"
    base_file.write_text("# base")

    # Checkpoint 1
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.create_checkpoint("Initial")

    # Agent creates file
    tool = WriteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id(dialog_id)

    import asyncio

    asyncio.run(tool.arun(tool_input={"path": "agent1.py", "content": "# agent1"}))

    # Checkpoint 2
    cp2 = tracker.create_checkpoint("Agent created agent1.py")

    # User creates file manually
    user_file = temp_project.root / "user_notes.txt"
    user_file.write_text("my notes")

    # Agent creates another file
    asyncio.run(tool.arun(tool_input={"path": "agent2.py", "content": "# agent2"}))

    # Checkpoint 3
    tracker.create_checkpoint("Agent created agent2.py")

    # Now restore to checkpoint 2
    tracker.restore_checkpoint(cp2.commit_id)

    # Expectations (standard git semantics):
    # - base.py: exists (was in cp2)
    # - agent1.py: exists (was in cp2)
    # - agent2.py: DELETED (in cp3, not in cp2)
    # - user_notes.txt: DELETED (in cp3, not in cp2)
    #
    # Note: user_notes.txt is deleted because it was included in cp3 via automatic scan.
    # Standard git restore semantics: diff HEAD vs target, delete files in HEAD but not in target.
    # If user wants to keep manual files, they should not checkpoint after creating them.

    assert base_file.exists()
    assert (temp_project.root / "agent1.py").exists()
    assert not (temp_project.root / "agent2.py").exists(), "agent2.py should be deleted"
    assert (
        not user_file.exists()
    ), "User file should be deleted (was in cp3, not in cp2)"


def test_restore_with_no_staged_changes(temp_project):
    """Test that restore works even when no files were staged between checkpoints."""
    dialog_id = temp_project.create_dialog(title="Test")

    # Checkpoint 1
    file1 = temp_project.root / "file1.py"
    file1.write_text("# initial")
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    cp1 = tracker.create_checkpoint("CP1")

    # Checkpoint 2: no changes, just another checkpoint
    tracker.create_checkpoint("CP2 - no changes")

    # Should not crash
    tracker.restore_checkpoint(cp1.commit_id)

    assert file1.exists()
