"""Tests that inspector dialog doesn't pollute index.json."""


def test_inspector_not_added_to_index(tmp_path):
    """Inspector dialog should not be added to index.json when saving messages."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    # Get inspector history and add messages
    inspector_history = project.get_dialog_history("inspector")
    inspector_history.add_user_message("Test message")
    inspector_history.add_ai_message("Test response")

    # Verify messages were saved
    messages = inspector_history.get_messages()
    assert len(messages) == 2

    # Verify inspector is NOT in index.json
    index = project.load_dialogs_index()
    dialog_ids = [d["id"] for d in index.get("dialogs", [])]
    assert "inspector" not in dialog_ids


def test_regular_dialog_added_to_index(tmp_path):
    """Regular dialogs should be added to index.json when saving messages."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    # Create regular dialog
    dialog_id = project.create_dialog(title="Test Dialog")

    # Get history and add messages
    history = project.get_dialog_history(dialog_id)
    history.add_user_message("Test message")
    history.add_ai_message("Test response")

    # Verify messages were saved
    messages = history.get_messages()
    assert len(messages) == 2

    # Verify dialog IS in index.json
    index = project.load_dialogs_index()
    dialog_ids = [d["id"] for d in index.get("dialogs", [])]
    assert dialog_id in dialog_ids


def test_inspector_uses_shared_storage(tmp_path):
    """Inspector should use shared journal.sqlite file."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    inspector_history = project.get_dialog_history("inspector")

    # Check that inspector uses journal.sqlite directly under dialogs/
    expected_path = project.dialogs_dir / "journal.sqlite"
    assert inspector_history.db_path == expected_path


def test_regular_dialog_uses_separate_storage(tmp_path):
    """Regular dialogs should use separate directories."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    dialog_id = project.create_dialog(title="Test Dialog")
    history = project.get_dialog_history(dialog_id)

    # Check that regular dialog uses its own subdirectory
    expected_path = project.dialogs_dir / dialog_id / "journal.sqlite"
    assert history.db_path == expected_path


def test_inspector_multiple_messages_not_in_index(tmp_path):
    """Adding multiple messages to inspector should not create index entries."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    inspector_history = project.get_dialog_history("inspector")

    # Add multiple messages
    for i in range(5):
        inspector_history.add_user_message(f"Message {i}")
        inspector_history.add_ai_message(f"Response {i}")

    # Verify all messages were saved
    messages = inspector_history.get_messages()
    assert len(messages) == 10

    # Verify inspector is still NOT in index.json
    index = project.load_dialogs_index()
    dialog_ids = [d["id"] for d in index.get("dialogs", [])]
    assert "inspector" not in dialog_ids


def test_inspector_clear_not_in_index(tmp_path):
    """Clearing inspector history should not create index entry."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    inspector_history = project.get_dialog_history("inspector")
    inspector_history.add_user_message("Message")
    inspector_history.clear()

    # Verify inspector is NOT in index.json
    index = project.load_dialogs_index()
    dialog_ids = [d["id"] for d in index.get("dialogs", [])]
    assert "inspector" not in dialog_ids


def test_track_metadata_flag(tmp_path):
    """Test that track_metadata flag controls index.json updates."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    from agentsmithy.core.project import set_workspace

    workspace = set_workspace(project_root)
    project = workspace.get_project(".")
    project.ensure_state_dir()
    project.ensure_dialogs_dir()

    # Inspector should have track_metadata=False
    inspector_history = project.get_dialog_history("inspector")
    assert inspector_history.track_metadata is False

    # Regular dialog should have track_metadata=True
    dialog_id = project.create_dialog(title="Test")
    regular_history = project.get_dialog_history(dialog_id)
    assert regular_history.track_metadata is True
