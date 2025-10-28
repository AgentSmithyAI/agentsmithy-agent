"""Test for checkpoint ignore pattern changes bug.

Reproduces issue where has_uncommitted_changes() returns True
when files that were in checkpoint are now ignored.
"""

import tempfile
from pathlib import Path

from agentsmithy.services.versioning import VersioningTracker


def test_has_uncommitted_changes_respects_new_ignore_patterns():
    """Test that has_uncommitted_changes() handles changed ignore patterns correctly.

    Scenario:
    1. Create checkpoint with files (manually, to include files that would normally be ignored)
    2. Add .gitignore pattern to ignore some of those files
    3. has_uncommitted_changes() should return False (files still exist, just ignored now)

    Bug: Currently returns True because it compares committed files (with old ignores)
    vs workdir files (with new ignores).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-ignore-change"

        # Create some files
        (project_root / "keep.txt").write_text("keep this")

        assets_dir = project_root / "Assets.xcassets"
        assets_dir.mkdir()
        (assets_dir / "image1.png").write_text("fake image 1")
        (assets_dir / "image2.png").write_text("fake image 2")
        (assets_dir / "Contents.json").write_text('{"version": 1}')

        # Manually create checkpoint that includes ALL files (bypassing DEFAULT_EXCLUDES)
        tracker = VersioningTracker(str(project_root), dialog_id)
        repo = tracker.ensure_repo()

        # Manually build tree with all files
        import time

        from dulwich.objects import Blob, Commit, Tree, parse_timezone

        # Create .gitignore BEFORE checkpoint (with empty content initially)
        gitignore = project_root / ".gitignore"
        gitignore.write_text("")

        # Create blobs for all files (including .gitignore)
        keep_blob = Blob.from_string((project_root / "keep.txt").read_bytes())
        img1_blob = Blob.from_string((assets_dir / "image1.png").read_bytes())
        img2_blob = Blob.from_string((assets_dir / "image2.png").read_bytes())
        json_blob = Blob.from_string((assets_dir / "Contents.json").read_bytes())
        gitignore_blob = Blob.from_string(gitignore.read_bytes())

        # Build tree structure
        assets_tree = Tree()
        assets_tree.add(b"image1.png", 0o100644, img1_blob.id)
        assets_tree.add(b"image2.png", 0o100644, img2_blob.id)
        assets_tree.add(b"Contents.json", 0o100644, json_blob.id)

        root_tree = Tree()
        root_tree.add(b".gitignore", 0o100644, gitignore_blob.id)
        root_tree.add(b"keep.txt", 0o100644, keep_blob.id)
        root_tree.add(b"Assets.xcassets", 0o040000, assets_tree.id)

        # Create commit
        commit = Commit()
        commit.tree = root_tree.id
        commit.parents = []
        commit.author = commit.committer = b"Test <test@test.com>"
        commit.commit_time = commit.author_time = int(time.time())
        commit.commit_timezone = commit.author_timezone = parse_timezone(b"+0000")[0]
        commit.message = b"Initial checkpoint with assets"

        # Save to repo
        repo.object_store.add_objects(
            [
                (gitignore_blob, None),
                (keep_blob, None),
                (img1_blob, None),
                (img2_blob, None),
                (json_blob, None),
                (assets_tree, None),
                (root_tree, None),
                (commit, None),
            ]
        )

        # Update session ref
        session_ref = tracker._get_session_ref("session_1")
        repo.refs[session_ref] = commit.id
        repo.refs[tracker.MAIN_BRANCH] = commit.id

        # Verify checkpoint includes all 5 files (.gitignore + keep.txt + 3 assets)
        tree = repo[root_tree.id]

        def count_files(tree_obj, repo_obj):
            count = 0
            from dulwich.objects import Tree

            for _name, _mode, sha in tree_obj.items():
                obj = repo_obj[sha]
                if isinstance(obj, Tree):
                    count += count_files(obj, repo_obj)
                else:
                    count += 1
            return count

        files_in_checkpoint = count_files(tree, repo)
        assert (
            files_in_checkpoint == 5
        ), f"Expected 5 files in checkpoint, got {files_in_checkpoint}"

        # Now UPDATE .gitignore to ignore Assets.xcassets
        gitignore.write_text("*.xcassets/\n")

        # Create new tracker instance to pick up new .gitignore
        tracker2 = VersioningTracker(str(project_root), dialog_id)

        # All files still exist on disk
        assert (project_root / "keep.txt").exists()
        assert (assets_dir / "image1.png").exists()
        assert (assets_dir / "image2.png").exists()
        assert (assets_dir / "Contents.json").exists()

        # Note: .gitignore content changed (empty -> "*.xcassets/\n")
        # BUT we're testing the case where committed files become ignored
        # The .gitignore change itself IS a legitimate uncommitted change,
        # so let's commit it first
        tracker2.ensure_repo()
        tracker2.create_checkpoint("Update .gitignore")

        # NOW check - no uncommitted changes expected
        # BUG (before fix): has_uncommitted_changes() would return True because:
        # - Committed files in FIRST checkpoint: 5 (.gitignore + keep.txt + 3 Assets.xcassets)
        # - Current files (with new ignore): 2 (.gitignore + keep.txt only, xcassets ignored)
        # - Difference: 3 files -> reports as "deleted"
        #
        # EXPECTED (after fix): Should return False because those 3 files are now ignored,
        # not actually deleted
        has_changes = tracker2.has_uncommitted_changes()

        # This should PASS after fix
        assert not has_changes, (
            "has_uncommitted_changes() should return False when files "
            "that were in checkpoint are now ignored by .gitignore"
        )


def test_has_uncommitted_changes_detects_real_deletion():
    """Test that real file deletions are still detected.

    Make sure our fix doesn't break detection of actual deletions.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-real-deletion"

        # Create files
        (project_root / "file1.txt").write_text("content 1")
        (project_root / "file2.txt").write_text("content 2")

        # Create checkpoint
        tracker = VersioningTracker(str(project_root), dialog_id)
        tracker.ensure_repo()
        tracker.create_checkpoint("Initial checkpoint")

        # Actually delete a file
        (project_root / "file2.txt").unlink()

        # Should detect the deletion
        has_changes = tracker.has_uncommitted_changes()
        assert has_changes, "Should detect real file deletion"


def test_has_uncommitted_changes_with_default_excludes():
    """Test the actual bug scenario with DEFAULT_EXCLUDES.

    Scenario:
    1. Checkpoint created before DEFAULT_EXCLUDES had *.xcassets/
    2. DEFAULT_EXCLUDES updated to include *.xcassets/
    3. has_uncommitted_changes() incorrectly reports changes
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        dialog_id = "test-dialog-default-excludes"

        # Create files including .xcassets
        (project_root / "main.swift").write_text("// main")

        assets_dir = project_root / "Resources.xcassets"
        assets_dir.mkdir()
        (assets_dir / "icon.png").write_text("fake icon")

        # Simulate old checkpoint that included .xcassets
        # (by temporarily removing *.xcassets/ from DEFAULT_EXCLUDES check)
        from agentsmithy.services.versioning import DEFAULT_EXCLUDES

        # Check that *.xcassets/ IS in DEFAULT_EXCLUDES
        has_xcassets_pattern = any("xcassets" in p for p in DEFAULT_EXCLUDES)
        assert has_xcassets_pattern, "*.xcassets/ should be in DEFAULT_EXCLUDES"

        # Even with *.xcassets/ in DEFAULT_EXCLUDES, if we create a checkpoint
        # and the files exist, checking should not report false uncommitted changes
        tracker = VersioningTracker(str(project_root), dialog_id)
        tracker.ensure_repo()

        # Create checkpoint (will respect current DEFAULT_EXCLUDES)
        checkpoint = tracker.create_checkpoint("Checkpoint with current excludes")

        # Verify that .xcassets files are NOT in the checkpoint
        repo = tracker.ensure_repo()
        commit = repo[checkpoint.commit_id.encode()]
        tree = repo[commit.tree]

        committed_files = set()
        from dulwich.objects import Tree

        def collect_files(tree_obj, repo_obj, prefix=""):
            for name, _mode, sha in tree_obj.items():
                decoded_name = name.decode("utf-8")
                full_path = f"{prefix}/{decoded_name}" if prefix else decoded_name
                obj = repo_obj[sha]
                if isinstance(obj, Tree):
                    collect_files(obj, repo_obj, full_path)
                else:
                    committed_files.add(full_path)

        collect_files(tree, repo)

        # Should only have main.swift, not .xcassets files
        assert "main.swift" in committed_files
        assert not any(".xcassets" in f for f in committed_files)

        # Now check - should have no uncommitted changes
        has_changes = tracker.has_uncommitted_changes()
        assert (
            not has_changes
        ), "Should have no uncommitted changes when ignores are consistent"
