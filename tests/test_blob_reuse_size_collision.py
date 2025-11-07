"""Test: Blob reuse must check content hash, not just size (size collision bug).

Reproduces bug where files with same size but different content were incorrectly
reused from project git, leading to wrong file versions in checkpoints.
"""


def test_blob_reuse_must_check_hash_not_just_size(temp_project):
    """Test that blob reuse checks content hash, not just file size."""
    from agentsmithy.services.versioning import VersioningTracker

    project = temp_project
    dialog_id = project.create_dialog(title="Test Dialog")
    project_root = project.root

    # Create a main git repo to simulate user's project git
    import subprocess

    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    # Create file with version 1 and commit to project git
    file_path = project_root / "code.py"
    v1 = "def foo():\n    return 1"
    file_path.write_text(v1)
    v1_size = file_path.stat().st_size

    subprocess.run(
        ["git", "add", "code.py"], cwd=project_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Version 1"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    tracker = VersioningTracker(str(project_root), dialog_id)

    # Create checkpoint - should reuse blob from project git
    cp1 = tracker.create_checkpoint("CP1")

    # Change file content but keep SAME SIZE (size collision!)
    v2 = "def foo():\n    return 2"
    file_path.write_text(v2)
    v2_size = file_path.stat().st_size
    assert (
        v2_size == v1_size
    ), f"Size must be same for this test: {v1_size} vs {v2_size}"

    # Commit to project git
    subprocess.run(
        ["git", "add", "code.py"], cwd=project_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Version 2"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    # Create checkpoint - MUST see the change despite same size
    cp2 = tracker.create_checkpoint("CP2")

    # Verify: CP2 must have different blob than CP1
    repo = tracker.ensure_repo()
    cp1_commit = repo[
        cp1.commit_id.encode() if isinstance(cp1.commit_id, str) else cp1.commit_id
    ]
    cp2_commit = repo[
        cp2.commit_id.encode() if isinstance(cp2.commit_id, str) else cp2.commit_id
    ]

    cp1_tree = repo[cp1_commit.tree]
    cp2_tree = repo[cp2_commit.tree]

    cp1_blob_id = None
    cp2_blob_id = None
    for name, _mode, sha in cp1_tree.items():
        if name == b"code.py":
            cp1_blob_id = sha
            break
    for name, _mode, sha in cp2_tree.items():
        if name == b"code.py":
            cp2_blob_id = sha
            break

    assert cp1_blob_id is not None, "code.py should exist in CP1"
    assert cp2_blob_id is not None, "code.py should exist in CP2"

    # Get actual content
    cp1_blob = repo[cp1_blob_id]
    cp2_blob = repo[cp2_blob_id]

    assert cp1_blob.data == b"def foo():\n    return 1", "CP1 should have version 1"
    assert (
        cp2_blob.data == b"def foo():\n    return 2"
    ), f"CP2 should have version 2 (size collision must be detected), got: {cp2_blob.data}"
    assert (
        cp1_blob_id != cp2_blob_id
    ), "Blobs must be different despite same size (size collision)"


def test_blob_reuse_after_code_formatting(temp_project):
    """Test blob reuse after code formatting (common real-world scenario)."""
    from agentsmithy.services.versioning import VersioningTracker

    project = temp_project
    dialog_id = project.create_dialog(title="Test Dialog")
    project_root = project.root

    # Create a main git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    # Create file with unformatted code
    file_path = project_root / "api.py"
    # Use strings with same length but different content
    unformatted = "x = (data.foo)"
    file_path.write_text(unformatted)
    unformatted_size = file_path.stat().st_size

    subprocess.run(
        ["git", "add", "api.py"], cwd=project_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Unformatted"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    tracker = VersioningTracker(str(project_root), dialog_id)
    _ = tracker.create_checkpoint("Before formatting")

    # Format code (same size but different content)
    formatted = "y = (data.bar)"
    file_path.write_text(formatted)
    formatted_size = file_path.stat().st_size
    assert (
        unformatted_size == formatted_size
    ), f"Test requires same size: {unformatted_size} vs {formatted_size}"

    subprocess.run(
        ["git", "add", "api.py"], cwd=project_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Formatted"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    # Create checkpoint after formatting
    cp2 = tracker.create_checkpoint("After formatting")

    # Verify: CP2 must have formatted version
    repo = tracker.ensure_repo()
    cp2_commit = repo[
        cp2.commit_id.encode() if isinstance(cp2.commit_id, str) else cp2.commit_id
    ]
    cp2_tree = repo[cp2_commit.tree]

    for name, _mode, sha in cp2_tree.items():
        if name == b"api.py":
            cp2_blob = repo[sha]
            assert (
                cp2_blob.data.decode() == formatted
            ), f"CP2 must have formatted version, got: {cp2_blob.data.decode()}"
            return

    raise AssertionError("api.py not found in CP2")
