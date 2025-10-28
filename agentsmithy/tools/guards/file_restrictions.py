"""
File restrictions module for controlling access to files and directories.
Contains hardcoded patterns for ignored directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FileRestrictions:
    """Controls file/directory access by enforcing ignore patterns."""

    # Default directories to ignore
    DEFAULT_IGNORE_DIRS = {
        "node_modules",
        "__pycache__",
        "env",
        "venv",
        ".venv",
        "dist",
        "out",
        "bundle",
        "vendor",
        "tmp",
        "temp",
        "deps",
        "Pods",
        ".git",
        ".github",
        ".cache",
        ".env",
    }

    # Special nested paths to ignore (will be checked separately)
    NESTED_IGNORE_PATTERNS = [
        ("target", "dependency"),
        ("build", "dependencies"),
    ]

    def __init__(self, workspace_root: str | Path):
        """Initialize FileRestrictions with a workspace root."""
        self.workspace_root = Path(workspace_root).resolve()

    def _is_dir_name_ignored(self, dir_name: str) -> bool:
        """Check if a directory name (not full path) should be ignored."""
        return dir_name in self.DEFAULT_IGNORE_DIRS

    def is_ignored_directory(self, path: Path) -> bool:
        """Check if a directory should be ignored based on default patterns."""
        try:
            # Get all parts of the path relative to workspace root
            rel_path = path.relative_to(self.workspace_root)
            parts = rel_path.parts

            # Check if any part of the path matches ignored directories
            for part in parts:
                if part in self.DEFAULT_IGNORE_DIRS:
                    return True

            # Check if the directory name itself (not full path) matches patterns
            dir_name = path.name
            if dir_name in self.DEFAULT_IGNORE_DIRS:
                return True

            # Special case for nested dependency paths
            # Check if path contains nested ignore patterns like target/dependency
            for parent_dir, child_dir in self.NESTED_IGNORE_PATTERNS:
                try:
                    # Find index of parent directory in parts
                    parent_idx = parts.index(parent_dir)
                    # Check if the next part is the child directory
                    if (
                        parent_idx + 1 < len(parts)
                        and parts[parent_idx + 1] == child_dir
                    ):
                        return True
                except ValueError:
                    # Parent directory not found in path
                    continue

        except ValueError:
            # Path is not relative to workspace root
            pass

        return False

    def is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        # Check if any parent directory is ignored
        try:
            rel_path = path.relative_to(self.workspace_root)
            # Check each parent directory
            for parent in rel_path.parents:
                parent_path = self.workspace_root / parent
                if parent_path.is_dir() and self.is_ignored_directory(parent_path):
                    return True
        except ValueError:
            # Path is not relative to workspace
            pass

        # Check if the path itself is an ignored directory
        if path.is_dir() and self.is_ignored_directory(path):
            return True

        return False

    def is_ignored_relative_to(self, path: Path, base: Path) -> bool:
        """
        Check if a path should be ignored relative to a base directory.

        This is used when listing contents of an explicitly requested directory.
        Only checks for ignored directories between base and path, not above base.

        Args:
            path: The path to check
            base: The base directory (explicitly requested by user)

        Returns:
            True if the path should be ignored, False otherwise
        """
        # Check if any parent directory between base and path is ignored
        try:
            rel_path = path.relative_to(base)
            # Check each part of the relative path
            for part in rel_path.parts:
                if self._is_dir_name_ignored(part):
                    return True
        except ValueError:
            # Path is not relative to base
            pass

        # Check if the path itself is an ignored directory (by name)
        if path.is_dir() and self._is_dir_name_ignored(path.name):
            return True

        return False

    def filter_paths(
        self, paths: list[Path | str], include_hidden: bool = False
    ) -> list[Path]:
        """Filter a list of paths, removing ignored ones."""
        filtered = []
        for p in paths:
            path = Path(p) if isinstance(p, str) else p
            # Check if path is ignored
            if self.is_ignored(path):
                continue
            # Check if hidden files should be included
            if not self.should_include_hidden(path, include_hidden):
                continue
            filtered.append(path)
        return filtered

    def should_include_hidden(self, path: Path, include_hidden_requested: bool) -> bool:
        """
        Determine if a hidden file/directory should be included.

        Args:
            path: The path to check
            include_hidden_requested: Whether user explicitly requested hidden files

        Returns:
            True if the path should be included, False otherwise
        """
        if not include_hidden_requested:
            # Check if any part of the path is hidden
            try:
                rel_path = path.relative_to(self.workspace_root)
                if any(part.startswith(".") for part in rel_path.parts):
                    return False
            except ValueError:
                # For absolute paths, just check the name
                if path.name.startswith("."):
                    return False

        return True

    def should_include_hidden_relative_to(
        self, path: Path, base: Path, include_hidden_requested: bool
    ) -> bool:
        """
        Determine if a hidden file/directory should be included relative to base.

        This is used when listing contents of an explicitly requested directory.
        Only checks for hidden parts between base and path, not above base.

        Args:
            path: The path to check
            base: The base directory (explicitly requested by user)
            include_hidden_requested: Whether user explicitly requested hidden files

        Returns:
            True if the path should be included, False otherwise
        """
        if not include_hidden_requested:
            # Check if any part of the path relative to base is hidden
            try:
                rel_path = path.relative_to(base)
                if any(part.startswith(".") for part in rel_path.parts):
                    return False
            except ValueError:
                # For absolute paths, just check the name
                if path.name.startswith("."):
                    return False

        return True

    def is_restricted_path(self, path: Path) -> bool:
        """
        Check if a path is restricted (e.g., root directory or home directory).

        Args:
            path: The path to check

        Returns:
            True if the path is restricted, False otherwise
        """
        try:
            # Check if it's root directory (cross-platform)
            if path.parts == (path.anchor,):
                return True

            # Check if it's home directory
            home = Path.home()
            if path == home:
                return True

        except Exception:
            pass

        return False

    def get_ignore_patterns_info(self) -> dict[str, Any]:
        """Get information about current ignore patterns."""
        return {
            "default_ignored_dirs": sorted(list(self.DEFAULT_IGNORE_DIRS)),
            "has_ignore_file": False,
        }


# Singleton instance for the current workspace
_restrictions_instance: FileRestrictions | None = None


def get_file_restrictions(workspace_root: str | Path) -> FileRestrictions:
    """Get or create a FileRestrictions instance for the workspace."""
    global _restrictions_instance

    workspace_root = Path(workspace_root).resolve()

    # Create new instance if needed
    if (
        _restrictions_instance is None
        or _restrictions_instance.workspace_root != workspace_root
    ):
        _restrictions_instance = FileRestrictions(workspace_root)

    return _restrictions_instance
