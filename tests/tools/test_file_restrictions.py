from __future__ import annotations

from pathlib import Path

from agentsmithy.tools.guards.file_restrictions import (
    FileRestrictions,
    get_file_restrictions,
)


class TestFileRestrictions:
    """Test suite for FileRestrictions class."""

    def test_default_ignored_directories(self, tmp_path: Path):
        """Test that default directories are properly ignored."""
        restrictions = FileRestrictions(tmp_path)

        # Create test directories
        test_dirs = [
            "node_modules",
            "__pycache__",
            ".git",
            ".venv",
            "dist",
            "regular_dir",
        ]

        for dir_name in test_dirs:
            test_dir = tmp_path / dir_name
            test_dir.mkdir()

            if dir_name == "regular_dir":
                assert not restrictions.is_ignored_directory(test_dir)
            else:
                assert restrictions.is_ignored_directory(test_dir)

    def test_nested_ignored_directories(self, tmp_path: Path):
        """Test that nested ignored directories are detected."""
        restrictions = FileRestrictions(tmp_path)

        # Create nested structure
        nested_path = tmp_path / "src" / "components" / "node_modules"
        nested_path.mkdir(parents=True)

        assert restrictions.is_ignored_directory(nested_path)
        assert not restrictions.is_ignored_directory(tmp_path / "src")
        assert not restrictions.is_ignored_directory(tmp_path / "src" / "components")

    def test_hidden_file_handling(self, tmp_path: Path):
        """Test hidden file detection."""
        restrictions = FileRestrictions(tmp_path)

        # Create test files
        visible_file = tmp_path / "visible.txt"
        hidden_file = tmp_path / ".hidden"
        nested_hidden = tmp_path / "dir" / ".config"

        visible_file.touch()
        hidden_file.touch()
        nested_hidden.mkdir(parents=True)

        # Test with include_hidden=False
        assert restrictions.should_include_hidden(visible_file, False)
        assert not restrictions.should_include_hidden(hidden_file, False)
        assert not restrictions.should_include_hidden(nested_hidden, False)

        # Test with include_hidden=True
        assert restrictions.should_include_hidden(visible_file, True)
        assert restrictions.should_include_hidden(hidden_file, True)
        assert restrictions.should_include_hidden(nested_hidden, True)

    def test_restricted_paths(self, tmp_path: Path, monkeypatch):
        """Test restricted path detection."""
        # Use isolated temp directory as workspace root, HOME and cwd
        # so checks don't depend on the real project/home paths.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        restrictions = FileRestrictions(tmp_path)

        # Test root directory
        assert restrictions.is_restricted_path(Path("/"))

        # Test home directory (now tmp_path)
        assert restrictions.is_restricted_path(tmp_path)

        # Test regular directories (not root/home)
        assert not restrictions.is_restricted_path(Path("/tmp") / "regular_dir")
        assert not restrictions.is_restricted_path(tmp_path / "subdir")

    def test_filter_paths(self, tmp_path: Path):
        """Test filtering multiple paths at once."""
        restrictions = FileRestrictions(tmp_path)

        # Create test structure
        paths = []
        for name in ["file1.txt", "node_modules/dep.js", ".hidden", "src/main.py"]:
            path = tmp_path / name
            if "/" in name:
                path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            paths.append(path)

        # Filter paths
        filtered = restrictions.filter_paths(paths)

        # Check results
        filtered_names = [p.name for p in filtered]
        filtered_full_paths = [str(p) for p in filtered]

        assert "file1.txt" in filtered_names
        assert "main.py" in filtered_names
        # Check that files in node_modules are filtered out
        assert not any("node_modules" in p for p in filtered_full_paths)
        # Hidden files should be filtered by default when include_hidden is False
        assert ".hidden" not in filtered_names

    def test_singleton_pattern(self, tmp_path: Path):
        """Test that get_file_restrictions returns the same instance."""
        restrictions1 = get_file_restrictions(tmp_path)
        restrictions2 = get_file_restrictions(tmp_path)

        assert restrictions1 is restrictions2

        # Different path should create new instance
        other_path = tmp_path / "subdir"
        other_path.mkdir()
        restrictions3 = get_file_restrictions(other_path)

        assert restrictions3 is not restrictions1

    def test_special_ignore_patterns(self, tmp_path: Path):
        """Test special ignore patterns like target/dependency."""
        restrictions = FileRestrictions(tmp_path)

        # Create nested dependency paths
        target_dep = tmp_path / "project" / "target" / "dependency" / "lib.jar"
        build_dep = tmp_path / "app" / "build" / "dependencies" / "module.so"

        target_dep.parent.mkdir(parents=True)
        build_dep.parent.mkdir(parents=True)

        assert restrictions.is_ignored_directory(target_dep.parent)
        assert restrictions.is_ignored_directory(build_dep.parent)

    def test_get_ignore_patterns_info(self, tmp_path: Path):
        """Test getting information about ignore patterns."""
        restrictions = FileRestrictions(tmp_path)
        info = restrictions.get_ignore_patterns_info()

        assert "default_ignored_dirs" in info
        assert "has_ignore_file" in info
        assert info["has_ignore_file"] is False
        assert len(info["default_ignored_dirs"]) > 0
