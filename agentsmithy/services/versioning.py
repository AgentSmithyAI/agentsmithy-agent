from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pathspec
from dulwich import porcelain
from dulwich.objects import Commit, Tree
from dulwich.repo import Repo

# Note: This module uses dulwich (pure Python git implementation) for all git operations.
# Git binary is not required - everything works through dulwich API.

"""
File Include/Exclude Logic
===========================

This module implements a comprehensive file tracking and exclusion system for checkpoints:

1. DEFAULT_EXCLUDES (defined below):
   - Hardcoded list of patterns that are ALWAYS excluded from automatic checkpoint scans
   - Includes build artifacts, caches, dependencies, virtual environments, etc.
   - Uses gitignore-style patterns (via pathspec library): directories (dir/), globs (*.pyc), etc.
   - Examples: .venv/, node_modules/, __pycache__/, *.pyc, dist/, build/

2. Project .gitignore:
   - If project has .gitignore file, patterns are loaded and combined with DEFAULT_EXCLUDES
   - Uses full gitignore specification (via pathspec library):
     * Directory patterns: .venv/ - matches directory and all its contents
     * Wildcards: *.log - matches all .log files
     * Negation: !important.log - includes file even if matched by earlier pattern
     * Anchored patterns: /config.json - only matches at root
     * Double-star: **/test/** - matches test directory anywhere

3. Git Staging Area (Index):
   - Files created or modified by agent tools (write_file, edit_file) are staged immediately
   - Each tool calls tracker.stage_file(path) which adds file to git index (staging area)
   - This is equivalent to "git add -f" - stages file even if it matches ignore patterns
   - Staged files persist in .agentsmithy/<dialog_id>/checkpoints/.git/index
   - Purpose: Force-add intentionally created files even if they match ignore patterns
   
4. Checkpoint Creation:
   - Step 1: Scan working directory, add all files EXCEPT those matching ignore patterns
   - Step 2: Merge staging area (index) into tree - adds staged files even if ignored
   - Step 3: Commit tree and clear staging area
   - Rationale: If agent explicitly calls write_file(".venv/config.py"), it's staged immediately,
     then force-added to checkpoint despite matching DEFAULT_EXCLUDES
   - Uses standard git staging workflow instead of custom tracking file

5. Checkpoint Restoration (restore_checkpoint):
   - Uses standard git semantics: diff HEAD vs target checkpoint
   - Collects files to delete from TWO sources:
     * Files in HEAD checkpoint tree
     * Files in staging area (index) - uncommitted but agent-created
   - Deletes files in (HEAD_files ∪ staged_files - target_files)
   - Restores files from target checkpoint tree
   - Clears staging area after restore
   - Cleans up empty directories left after file deletion
   - Example scenario (non-ignored files):
     * Checkpoint 1: main.py, README.md
     * Agent creates: .github/workflows/ci.yaml (via write_file → staged to git index immediately)
     * Checkpoint 2: scans workdir + merges staging → includes .github/workflows/ci.yaml
     * Reset to checkpoint 1: .github/workflows/ci.yaml deleted (in checkpoint 2, not in checkpoint 1)
     * User manually creates: .local/myfile (not staged, not in checkpoint) → NOT deleted
   - Example scenario (ignored files):
     * Checkpoint 1: main.py
     * Agent creates: .venv/config.py (via write_file → staged to git index despite .venv/ in DEFAULT_EXCLUDES)
     * Checkpoint 2: scans workdir (skips .venv/) + merges staging → includes .venv/config.py (force-added from staging)
     * Staging cleared after checkpoint 2
     * Reset to checkpoint 1: .venv/config.py deleted (was in checkpoint 2)
     * User creates: .venv/lib/package.py (not staged) → NOT deleted (not in any checkpoint)
   - Example scenario (staged but not committed):
     * Checkpoint 1: main.py
     * Agent creates: .github/workflows/ci.yaml (via write_file → staged, but NO checkpoint created yet)
     * Reset to checkpoint 1: .github/workflows/ci.yaml deleted (staged but not in checkpoint 1)
     * Staging cleared after restore

6. Uncommitted Changes Detection (has_uncommitted_changes):
   - Compares current working directory against HEAD checkpoint
   - Uses CURRENT ignore spec (from .gitignore + DEFAULT_EXCLUDES)
   - Filters committed files by current ignore spec before comparison
   - Prevents false positives when files become ignored after being committed
   - Example: .xcassets/ files committed before DEFAULT_EXCLUDES update → now ignored → not counted as "deleted"

Key Design Principles:
- Respect ignore patterns for automatic scans: Don't include artifacts/caches by default
- Trust explicit actions: If agent explicitly creates a file, stage it immediately (git add -f)
- Use standard git workflow: Staging area (index) for force-adds, not custom tracking files
- Standard git semantics: Restore = diff and apply, staging = force-add mechanism
- Handle pattern changes gracefully: Files can become ignored after being committed
- Clean up after ourselves: Clear staging after checkpoint, delete outdated files on restore
"""

# Comprehensive list of build artifacts, caches, and dependencies across languages
DEFAULT_EXCLUDES = [
    # Version control
    ".git/",
    ".svn/",
    ".hg/",
    # Agent state
    ".agentsmithy/",
    "chroma_db/",
    # Python
    ".venv/",
    "venv/",
    "env/",
    ".env/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".tox/",
    ".coverage",
    ".coverage.*",
    "coverage/",
    "coverage.xml",
    "htmlcov/",
    "*.egg-info/",
    "dist/",
    "build/",
    "Build/",
    "build-*/",
    ".eggs/",
    "pip-wheel-metadata/",
    "__pypackages__/",
    ".ipynb_checkpoints/",
    ".hypothesis/",
    ".nox/",
    ".benchmarks/",
    ".python-version",
    # Node.js / JavaScript / TypeScript
    "node_modules/",
    ".npm/",
    ".yarn/",
    ".pnpm-store/",
    "npm-debug.log*",
    "pnpm-debug.log*",
    "yarn-error.log*",
    "lerna-debug.log*",
    ".eslintcache",
    "*.tsbuildinfo",
    ".parcel-cache/",
    ".turbo/",
    ".vite/",
    ".svelte-kit/",
    ".angular/cache/",
    "jspm_packages/",
    "bower_components/",
    ".next/",
    ".nuxt/",
    "out/",
    ".cache/",
    ".expo/",
    ".vercel/",
    ".firebase/",
    # Java / Kotlin / Scala
    "target/",
    ".gradle/",
    ".m2/",
    ".settings/",
    ".classpath",
    ".project",
    "*.class",
    "*.jar",
    "*.war",
    "*.ear",
    # Java/Scala IDE & tooling
    "*.iml",
    ".bsp/",
    ".bloop/",
    ".metals/",
    ".scala-build/",
    ".coursier/",
    ".nb-gradle/",
    "nbbuild/",
    "nbproject/private/",
    # JVM crash logs
    "hs_err_pid*.log",
    "replay_pid*.log",
    # C / C++ / MSVC
    "*.o",
    "*.obj",
    "*.exe",
    "*.out",
    "*.a",
    "*.lib",
    "*.so",
    "*.dylib",
    "*.dll",
    "cmake-build-*/",
    "CMakeFiles/",
    "CMakeCache.txt",
    "Debug/",
    "Release/",
    "x64/",
    "x86/",
    ".vs/",
    # Rust
    "target/",
    "Cargo.lock",  # often auto-generated
    # Go
    "vendor/",
    "*.test",
    # .NET / C#
    "bin/",
    "obj/",
    "*.dll",
    "*.exe",
    "*.pdb",
    # Ruby
    ".bundle/",
    "vendor/bundle/",
    "*.gem",
    # PHP
    "vendor/",
    "composer.lock",  # often auto-generated
    # Swift / iOS
    ".build/",
    "DerivedData/",
    "*.xcworkspace",
    "Pods/",
    "*.ipa",
    "*.xcassets/",  # Asset catalogs (images)
    "*.app/",
    "*.framework/",
    "*.dSYM/",
    # Android
    ".gradle/",
    "build/",
    "*.apk",
    "*.aab",
    "local.properties",
    # Databases
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    # IDEs and editors (user-specific, often in .gitignore)
    ".idea/",
    # Keep most of .idea/ ignored, but allow project-level text settings
    "!.idea/codeStyles/**",
    "!.idea/inspectionProfiles/**",
    "!.idea/runConfigurations/**",
    "!.idea/dictionaries/**",
    "!.idea/workspace.xml",
    # CI/CD and VCS text configs should be tracked
    "!.github/",
    "!.github/workflows/**",
    "!.github/ISSUE_TEMPLATE/**",
    "!.github/PULL_REQUEST_TEMPLATE/**",
    "!.github/dependabot.yml",
    "!.github/CODEOWNERS",
    "!.gitlab-ci.yml",
    "!.circleci/config.yml",
    # Common repo-level config files
    "!.editorconfig",
    "!.gitattributes",
    "!.gitignore",
    "!.dockerignore",
    "!.pre-commit-config.yaml",
    "!.prettier*",
    "!.eslintrc*",
    "!.stylelintrc*",
    # VS Code project settings are useful to track
    # (settings.json, tasks.json, launch.json, extensions.json, etc.)
    # So we do NOT exclude .vscode/ by default.
    ".fleet/",
    ".history/",
    ".vs/",
    ".DS_Store",
    "Thumbs.db",
    "ehthumbs.db",
    "desktop.ini",
    "Icon?",
    # Logs
    "*.log",
    "logs/",
    ".nyc_output/",
    # Temporary files
    "tmp/",
    ".tmp/",
    "temp/",
    "*.tmp",
    "*.bak",
    "*.swp",
    "*.swo",
    "*~",
    "*.orig",
    "*.rej",
    # Data science / ML
    ".dvc/",
    ".dvc/cache/",
    ".jupyter_cache/",
    # Infra
    ".terraform/",
    ".terragrunt-cache/",
]

# Number of failure entries to include in error messages
MAX_FAILURE_SAMPLES = 5


def stable_hash(text: str) -> str:
    """Generate stable 13-character SHA1 hash of text.

    Args:
        text: Text to hash

    Returns:
        First 13 characters of SHA1 hex digest
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:13]


def _build_gitignore_spec(gitignore_path: Path) -> pathspec.PathSpec:
    """Build PathSpec from .gitignore file and DEFAULT_EXCLUDES.

    Uses pathspec library for full gitignore specification support including:
    - Negation patterns (!pattern)
    - Anchored patterns (/pattern)
    - Directory patterns (foo/)
    - Wildcards and globs (*, ?, **)
    - All standard gitignore matching rules

    Args:
        gitignore_path: Path to .gitignore file

    Returns:
        PathSpec object that can match paths against gitignore patterns
    """
    patterns = []

    # Load patterns from .gitignore if exists
    if gitignore_path.exists():
        for line in gitignore_path.read_text().splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            patterns.append(line)

    # Add default excludes
    patterns.extend(DEFAULT_EXCLUDES)

    # Build PathSpec using gitwildmatch pattern (standard gitignore)
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


@dataclass
class CheckpointInfo:
    commit_id: str
    message: str


class VersioningTracker:
    """Shadow-repo versioning isolated from project's own Git.

    - Each dialog has its own repo: {project_root}/.agentsmithy/dialogs/{dialog_id}/checkpoints/
    - Uses branches: main (approved) + session_N (work sessions)
    - Uses non-bare repository to track project files
    - Does not touch user's main .git in the project

    Note: Uses dulwich (pure Python) for all git operations.
    Git binary is not required on the system.
    """

    MAIN_BRANCH = b"refs/heads/main"

    def __init__(self, project_root: str, dialog_id: str | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.dialog_id = dialog_id

        # Use dialog-specific directory if dialog_id provided
        if dialog_id:
            self.shadow_root = (
                self.project_root
                / ".agentsmithy"
                / "dialogs"
                / dialog_id
                / "checkpoints"
            )
        else:
            # Fallback for compatibility
            self.shadow_root = self.project_root / ".agentsmithy" / "checkpoints"

        self.shadow_root.mkdir(parents=True, exist_ok=True)
        self._tmp_dir: Path | None = None
        self._preedit_snapshots: dict[Path, bytes] = {}

        # Transaction support - group multiple file operations into one checkpoint
        self._transaction_active: bool = False
        self._transaction_files: list[str] = []
        self._transaction_message_parts: list[str] = []

    # ---- repo management ----
    def ensure_repo(self) -> Repo:
        """Ensure shadow git repository exists.

        Uses dulwich.porcelain.init() - pure Python, git binary not required.
        """
        # Use a non-bare repository that can track files in project directory
        git_dir = self.shadow_root / ".git"
        if git_dir.exists():
            repo = Repo(str(self.shadow_root))
        else:
            self.shadow_root.mkdir(parents=True, exist_ok=True)
            try:
                # Create non-bare repo
                repo = porcelain.init(path=str(self.shadow_root), bare=False)
            except FileExistsError:
                # Partial init or concurrent init; open existing
                repo = Repo(str(self.shadow_root))

        # Configure git
        cfg = repo.get_config()
        try:
            cfg.set((b"user",), b"name", b"AgentSmithy Versioning")
            cfg.set((b"user",), b"email", b"versioning@agentsmithy.local")
            # Persist config if supported
            if hasattr(cfg, "write_to_path"):
                cfg.write_to_path()
        except Exception:
            # Best-effort config; continue even if setting fails
            pass

        # Ensure initial commit exists (only if no commits at all)
        try:
            _ = repo.head()
        except Exception:
            # No commits yet - this is ok, first checkpoint will create the initial commit
            pass

        self._write_excludes(repo)
        self._ensure_branches_exist(repo)
        return repo

    def _write_excludes(self, repo: Repo) -> None:
        """Write exclude patterns to shadow repository's info/exclude file.

        Merges project's .gitignore patterns with DEFAULT_EXCLUDES.

        Args:
            repo: Shadow repository
        """
        info_dir = Path(repo.path) / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_file = info_dir / "exclude"
        # merge project .gitignore if exists
        patterns: list[str] = []
        gitignore = self.project_root / ".gitignore"
        if gitignore.exists():
            patterns.extend(
                [
                    line.strip()
                    for line in gitignore.read_text().splitlines()
                    if line.strip()
                ]
            )
        patterns.extend(DEFAULT_EXCLUDES)
        exclude_file.write_text("\n".join(sorted(set(patterns))) + "\n")

    # ---- edit attempt snapshots ----
    def start_edit(self, paths: Iterable[str]) -> None:
        """Snapshot files before editing to allow rollback on failure.

        Args:
            paths: Relative paths to files to snapshot
        """
        self._preedit_snapshots.clear()
        for p in paths:
            abs_path = (self.project_root / p).resolve()
            if abs_path.is_file():
                self._preedit_snapshots[abs_path] = abs_path.read_bytes()
        if self._preedit_snapshots:
            self._tmp_dir = Path(tempfile.mkdtemp(prefix="asm_preedit_"))

    def abort_edit(self) -> None:
        """Restore files from pre-edit snapshots and clean up."""
        for abs_path, content in self._preedit_snapshots.items():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(content)
        self._cleanup_edit()

    def finalize_edit(self) -> None:
        """Finalize edit without restoring snapshots (changes are kept)."""
        self._cleanup_edit()

    def _cleanup_edit(self) -> None:
        self._preedit_snapshots.clear()
        if self._tmp_dir and self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._tmp_dir = None

    # ---- transactions ----
    def begin_transaction(self) -> None:
        """Start a transaction to group multiple file operations into one checkpoint."""
        self._transaction_active = True
        self._transaction_files = []
        self._transaction_message_parts = []

    def stage_file(self, file_path: str) -> None:
        """Stage file in git index for force-add to next checkpoint.

        This is equivalent to 'git add -f' - adds file to staging even if ignored.
        Staged files will be included in next checkpoint regardless of ignore patterns.

        Args:
            file_path: Path to file relative to project root
        """
        try:
            repo = self.ensure_repo()
            abs_path = self.project_root / file_path

            if not abs_path.exists():
                return

            # Read file content and create blob
            from dulwich.objects import Blob

            content = abs_path.read_bytes()
            blob = Blob.from_string(content)
            repo.object_store.add_object(blob)

            # Add to git index (staging area)
            from dulwich.index import IndexEntry

            index = repo.open_index()

            # Get file stats for index entry
            stat = abs_path.stat()

            # Create index entry
            entry = IndexEntry(
                ctime=(int(stat.st_ctime), 0),
                mtime=(int(stat.st_mtime), 0),
                dev=stat.st_dev,
                ino=stat.st_ino,
                mode=stat.st_mode,
                uid=stat.st_uid,
                gid=stat.st_gid,
                size=stat.st_size,
                sha=blob.id,
                flags=0,
            )

            # Add entry to index
            index[file_path.encode("utf-8")] = entry
            index.write()

        except Exception as e:
            # Best effort - don't fail if staging fails
            from agentsmithy.utils.logger import agent_logger

            agent_logger.debug("Failed to stage file", file=file_path, error=str(e))

    def track_file_change(self, file_path: str, operation: str) -> None:
        """Track a file change within the current transaction.

        Args:
            file_path: Path to the changed file (relative to project root)
            operation: Type of operation (e.g., "write", "replace", "delete")
        """
        if self._transaction_active:
            if file_path not in self._transaction_files:
                self._transaction_files.append(file_path)
            self._transaction_message_parts.append(f"{operation}: {file_path}")

    def commit_transaction(self, message: str | None = None) -> CheckpointInfo | None:
        """Commit the current transaction and create a single checkpoint.

        Args:
            message: Optional custom message. If None, auto-generates from tracked changes.

        Returns:
            CheckpointInfo if checkpoint was created, None if no changes tracked
        """
        if not self._transaction_active:
            # No transaction active, fallback to regular checkpoint
            if message:
                return self.create_checkpoint(message)
            return None

        # Build commit message
        if message:
            commit_msg = message
        elif self._transaction_message_parts:
            commit_msg = (
                f"Transaction: {len(self._transaction_files)} files\n"
                + "\n".join(self._transaction_message_parts)
            )
        else:
            commit_msg = "Empty transaction"

        # Create checkpoint
        checkpoint = self.create_checkpoint(commit_msg)

        # Reset transaction state
        self._transaction_active = False
        self._transaction_files = []
        self._transaction_message_parts = []

        return checkpoint

    def abort_transaction(self) -> None:
        """Abort the current transaction without creating a checkpoint."""
        self._transaction_active = False
        self._transaction_files = []
        self._transaction_message_parts = []

    def is_transaction_active(self) -> bool:
        """Check if a transaction is currently active."""
        return self._transaction_active

    # ---- helper methods for checkpoint creation ----
    def _get_ignore_spec(self) -> pathspec.PathSpec:
        """Load and build PathSpec from gitignore patterns and defaults.

        Returns:
            PathSpec object for matching paths against gitignore patterns
        """
        gitignore = self.project_root / ".gitignore"
        return _build_gitignore_spec(gitignore)

    def _open_project_git(self) -> tuple[Any | None, Any | None]:
        """Try to open project git repository for blob reuse optimization.

        If project is a git repository, we can reuse existing blob objects
        for unchanged files, avoiding reading large files (images, etc.) into memory.
        Uses pure dulwich API - git binary not required.

        Returns:
            Tuple of (project_git_repo, project_git_tree) or (None, None)
        """
        try:
            project_git_path = self.project_root / ".git"
            if not project_git_path.exists() or not project_git_path.is_dir():
                return None, None

            from dulwich.repo import Repo as ProjectRepo

            from agentsmithy.utils.logger import agent_logger

            project_git_repo = ProjectRepo(str(self.project_root))

            # Get HEAD tree for blob lookup
            try:
                head_commit = project_git_repo[project_git_repo.head()]
                project_git_tree = project_git_repo[head_commit.tree]  # type: ignore[attr-defined]
                agent_logger.debug(
                    "Project git repo found, will reuse blobs for unchanged files"
                )
                return project_git_repo, project_git_tree
            except Exception:
                # No HEAD yet or empty repo
                return project_git_repo, None
        except Exception:
            # Project is not a git repo
            return None, None

    def _try_reuse_blob(
        self,
        file_path: Path,
        file_path_str: str,
        project_git_repo: Any,
        project_git_tree: Any,
    ) -> Any | None:
        """Try to reuse blob from project git if file unchanged.

        Args:
            file_path: Absolute path to file
            file_path_str: Relative path as string
            project_git_repo: Project git repository
            project_git_tree: Project git HEAD tree

        Returns:
            Blob object if reused, None otherwise
        """
        if project_git_tree is None or project_git_repo is None:
            return None

        try:
            # Look up file in project git tree
            tree_entry = project_git_tree.lookup_path(
                project_git_repo.__getitem__,
                file_path_str.encode("utf-8"),
            )
            if tree_entry and len(tree_entry) == 2:
                _mode, existing_blob_sha = tree_entry
                # Quick heuristic: check if file size matches blob size
                # Note: this is not a guarantee of equality (size collision possible),
                # but it's a fast optimization to avoid reading large files
                existing_blob = project_git_repo[existing_blob_sha]
                file_size = file_path.stat().st_size
                if len(existing_blob.data) == file_size:
                    # File likely unchanged based on size, reuse blob (no file read!)
                    return existing_blob
        except (KeyError, FileNotFoundError, AttributeError):
            # File not in project git or lookup failed
            pass
        except Exception:
            # Any other error (decompression, corruption, etc.) - fallback to reading file
            pass

        return None

    def _create_blob_for_file(
        self,
        file_path: Path,
        file_path_str: str,
        repo: Any,
        project_git_repo: Any,
        project_git_tree: Any,
    ) -> tuple[Any, bool]:
        """Create or reuse blob for a file.

        Args:
            file_path: Absolute path to file
            file_path_str: Relative path as string
            repo: Shadow repository
            project_git_repo: Project git repository (or None)
            project_git_tree: Project git HEAD tree (or None)

        Returns:
            Tuple of (blob, was_reused)
        """
        from dulwich.objects import Blob

        # Try to reuse blob from project git
        blob = self._try_reuse_blob(
            file_path, file_path_str, project_git_repo, project_git_tree
        )

        if blob is not None:
            return blob, True  # Don't add to repo yet, will batch later

        # Create new blob by reading file
        content = file_path.read_bytes()
        blob = Blob.from_string(content)
        return blob, False  # Don't add to repo yet, will batch later

    def _build_tree_from_workdir(
        self,
        repo: Any,
        ignore_spec: pathspec.PathSpec,
        project_git_repo: Any,
        project_git_tree: Any,
    ) -> tuple[Any, int, int]:
        """Build git tree by scanning project working directory.

        Uses parallel file processing for better performance with many files.

        Args:
            repo: Shadow repository
            ignore_spec: PathSpec object for gitignore pattern matching
            project_git_repo: Project git repository (or None)
            project_git_tree: Project git HEAD tree (or None)

        Returns:
            Tuple of (tree, blobs_reused, blobs_created)
        """
        import os
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from dulwich.objects import Tree

        tree: Tree = Tree()
        blobs_reused = 0
        blobs_created = 0

        # Collect all files first
        files_to_process: list[tuple[Path, str]] = []

        for root, dirs, files in os.walk(self.project_root):
            root_path = Path(root)
            rel_root = (
                root_path.relative_to(self.project_root)
                if root_path != self.project_root
                else Path(".")
            )

            # Filter directories
            filtered_dirs = []
            for d in dirs:
                dir_rel_path = (rel_root / d) if rel_root != Path(".") else Path(d)
                dir_path_str = str(dir_rel_path).replace("\\", "/")

                if not ignore_spec.match_file(dir_path_str):
                    filtered_dirs.append(d)

            dirs[:] = filtered_dirs

            # Collect files for parallel processing
            for filename in files:
                file_path = Path(root) / filename
                file_rel_path = file_path.relative_to(self.project_root)
                file_path_str = str(file_rel_path).replace("\\", "/")

                if not ignore_spec.match_file(file_path_str):
                    files_to_process.append((file_path, file_path_str))

        # Process files in parallel with thread pool
        blobs_to_add: list[Any] = []
        failed_files: list[tuple[str, str]] = []  # (file_path, error_msg)

        def process_file(
            file_info: tuple[Path, str],
        ) -> tuple[Any, str, bool] | tuple[None, str, str]:
            """Process single file and return a tagged union:
            - (blob, path, was_reused: bool) on success
            - (None, path, error_msg: str) on failure
            """
            file_path, file_path_str = file_info
            try:
                blob, was_reused = self._create_blob_for_file(
                    file_path,
                    file_path_str,
                    repo,
                    project_git_repo,
                    project_git_tree,
                )
                return blob, file_path_str, was_reused
            except Exception as e:
                return None, file_path_str, str(e)

        # Use thread pool for I/O parallelism
        max_workers = min(32, (len(files_to_process) or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(process_file, file_info)
                for file_info in files_to_process
            ]

            for future in as_completed(futures):
                result = future.result()
                blob, file_path_str, third = result

                if blob is not None:
                    # Success case: third is bool (was_reused)
                    blobs_to_add.append(blob)

                    if third:  # was_reused is True
                        blobs_reused += 1
                    else:
                        blobs_created += 1

                    # Add to tree
                    tree_path = file_path_str.encode("utf-8")
                    tree.add(tree_path, 0o100644, blob.id)
                else:
                    # Failure case: third is str (error_msg)
                    error_msg = str(third)
                    failed_files.append((file_path_str, error_msg))

        # Check if any files failed to process
        if failed_files:
            from agentsmithy.utils.logger import agent_logger

            agent_logger.error(
                "Failed to process files during checkpoint creation",
                failed_count=len(failed_files),
                total_files=len(files_to_process),
            )
            # Show first few failures in error message
            sample_failures = failed_files[:MAX_FAILURE_SAMPLES]
            failure_details = "\n".join(
                f"  - {path}: {err}" for path, err in sample_failures
            )
            more_info = (
                f"\n  ... and {len(failed_files) - MAX_FAILURE_SAMPLES} more"
                if len(failed_files) > MAX_FAILURE_SAMPLES
                else ""
            )
            raise RuntimeError(
                f"Failed to process {len(failed_files)} file(s) during checkpoint creation:\n"
                f"{failure_details}{more_info}"
            )

        # Batch add all blobs to object store
        if blobs_to_add:
            repo.object_store.add_objects([(blob, None) for blob in blobs_to_add])

        return tree, blobs_reused, blobs_created

    def _merge_staging_into_tree(self, tree: Any, repo: Any) -> int:
        """Merge staging area (index) into tree.

        Files in staging area were explicitly added via stage_file() (git add -f).
        Add them to tree even if they would be ignored by normal scan.

        Args:
            tree: Tree to merge staged files into
            repo: Repository object

        Returns:
            Number of files merged from staging
        """
        try:
            index = repo.open_index()
        except (FileNotFoundError, OSError) as e:
            # No index file - nothing to merge
            from agentsmithy.utils.logger import agent_logger

            agent_logger.debug("No index file to merge", error=str(e))
            return 0

        forced_count = 0

        for path, entry in index.items():
            try:
                # IndexEntry has attributes, not tuple indexing
                blob_id = entry.sha
                mode = entry.mode

                # Add to tree (overwrites if already exists)
                tree.add(path, mode, blob_id)
                forced_count += 1
            except Exception as e:
                # Best effort - skip entries that can't be processed
                from agentsmithy.utils.logger import agent_logger

                agent_logger.debug(
                    "Failed to merge staging entry", path=path, error=str(e)
                )

        return forced_count

    # ---- session management ----
    def _get_session_ref(self, session_name: str) -> bytes:
        """Get git ref for a session."""
        return f"refs/heads/{session_name}".encode()

    def _get_active_session_name(self) -> str:
        """Get active session name from database."""
        if not self.dialog_id:
            return "session_1"

        try:
            from agentsmithy.db.sessions import get_active_session

            db_path = self.shadow_root.parent / "journal.sqlite"
            if not db_path.exists():
                return "session_1"

            session = get_active_session(db_path)
            return session if session else "session_1"
        except Exception:
            return "session_1"

    def _get_db_path(self) -> Path:
        """Get path to dialog database."""
        return self.shadow_root.parent / "journal.sqlite"

    def _create_session(self, session_name: str, from_commit: bytes) -> None:
        """Create a new session branch from a commit."""
        repo = self.ensure_repo()
        session_ref = self._get_session_ref(session_name)
        repo.refs[session_ref] = from_commit

        # Force write ref to file (same as in create_checkpoint)
        try:
            git_dir = Path(repo.path)
            if git_dir.name == "checkpoints":
                git_dir = git_dir / ".git"
            ref_path = git_dir / session_ref.decode()
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(from_commit.decode() + "\n")
        except Exception:
            pass

        # Set HEAD to new session
        repo.refs[b"HEAD"] = b"ref: " + session_ref

    def _ensure_branches_exist(self, repo: Repo) -> None:
        """Ensure main and active session branches exist."""
        try:
            head = repo.head()

            # Create main branch if doesn't exist
            if self.MAIN_BRANCH not in repo.refs:
                repo.refs[self.MAIN_BRANCH] = head

            # Get or create active session
            active_session = self._get_active_session_name()
            session_ref = self._get_session_ref(active_session)

            # Only create session if it doesn't exist yet
            # Check the ref file directly to avoid symref loops
            session_ref_file = Path(repo.path) / session_ref.decode()

            if not session_ref_file.exists():
                # Create session from main
                main_head = repo.refs[self.MAIN_BRANCH]
                # Create session branch pointing to main HEAD (not symref, actual commit)
                repo.refs[session_ref] = main_head
            else:
                # Check if it's a valid commit SHA (not a symref)
                content = session_ref_file.read_text().strip()
                if content.startswith("ref:"):
                    # It's a symref (broken), recreate
                    session_ref_file.unlink()
                    main_head = repo.refs[self.MAIN_BRANCH]
                    repo.refs[session_ref] = main_head

            # Always ensure HEAD points to active session
            # Write symref directly to avoid dulwich following the ref
            head_file = Path(repo.path) / "HEAD"
            expected_ref = f"ref: {session_ref.decode()}\n"
            current_content = head_file.read_text() if head_file.exists() else ""
            if current_content != expected_ref:
                head_file.write_text(expected_ref)

        except Exception:
            # No commits yet, branches will be created on first checkpoint
            pass

    # ---- checkpoints ----
    def create_checkpoint(self, message: str) -> CheckpointInfo:
        """Create a checkpoint of current project state.

        Args:
            message: Checkpoint message

        Returns:
            CheckpointInfo with commit ID and message
        """
        import time

        from dulwich.objects import Commit, parse_timezone

        repo = self.ensure_repo()

        # Get parent commit from active session
        active_session = self._get_active_session_name()
        session_ref = self._get_session_ref(active_session)
        parent_commit = None
        try:
            if session_ref in repo.refs:
                parent_commit = repo[repo.refs[session_ref]]
            else:
                parent_commit = repo[repo.head()]
        except Exception:
            parent_commit = None

        # Load ignore spec
        ignore_spec = self._get_ignore_spec()

        # Try to open project git for blob reuse optimization
        project_git_repo, project_git_tree = self._open_project_git()

        # Build tree by scanning working directory
        tree, blobs_reused, blobs_created = self._build_tree_from_workdir(
            repo, ignore_spec, project_git_repo, project_git_tree
        )

        # Merge staging area (index) into tree
        # Files in staging were explicitly added via stage_file() (git add -f equivalent)
        # Include them even if they match ignore patterns
        forced_count = self._merge_staging_into_tree(tree, repo)
        if forced_count > 0:
            blobs_created += forced_count

        # Log blob statistics
        if blobs_reused > 0 or blobs_created > 0:
            from agentsmithy.utils.logger import agent_logger

            agent_logger.info(
                "Checkpoint blob statistics",
                reused=blobs_reused,
                created=blobs_created,
                total=blobs_reused + blobs_created,
            )

        # Save tree to repository
        repo.object_store.add_object(tree)

        # Create commit object
        commit: Commit = Commit()
        commit.tree = tree.id
        commit.parents = [parent_commit.id] if parent_commit else []
        commit.author = commit.committer = (
            b"AgentSmithy Versioning <versioning@agentsmithy.local>"
        )
        commit.commit_time = commit.author_time = int(time.time())
        commit.commit_timezone = commit.author_timezone = parse_timezone(b"+0000")[0]
        commit.message = message.encode("utf-8")

        # Save commit and update session branch
        repo.object_store.add_object(commit)

        # Update session branch ref
        old_value = (
            repo.refs.read_ref(session_ref) if session_ref in repo.refs else None
        )
        if not repo.refs.set_if_equals(session_ref, old_value, commit.id):
            # Fallback to direct assignment if CAS fails
            repo.refs[session_ref] = commit.id

        # Force write ref to file (dulwich may keep it in memory/packed-refs)
        # This ensures new Repo instances can see the update
        try:
            # repo.path points to .git directory, refs are at .git/refs/heads/...
            git_dir = Path(repo.path)
            if git_dir.name == "checkpoints":
                git_dir = git_dir / ".git"
            ref_path = git_dir / session_ref.decode()
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(commit.id.decode() + "\n")
        except Exception:
            pass  # Non-critical

        # Initialize main branch if this is first commit
        if not commit.parents and self.MAIN_BRANCH not in repo.refs:
            repo.refs[self.MAIN_BRANCH] = commit.id

        # Record metadata
        commit_id = commit.id.decode("utf-8")
        self._record_metadata(commit_id, message)

        # NOTE: We do NOT clear staging area here because restore_checkpoint()
        # needs to read it to know which files to delete. Index is cleared in
        # restore_checkpoint() and clear_staging() instead.

        return CheckpointInfo(commit_id=commit_id, message=message)

    def _collect_tree_files(
        self, tree_obj: Tree, repo: Any, prefix: str = ""
    ) -> set[str]:
        """Recursively collect all file paths from a git tree.

        Uses pure dulwich API - git binary not required.
        Replaces subprocess-based 'git ls-tree -r --name-only'.

        Args:
            tree_obj: Tree object to traverse
            repo: Repository object
            prefix: Path prefix for recursion

        Returns:
            Set of file paths
        """
        files: set[str] = set()

        for name, _mode, sha in tree_obj.items():
            decoded_name = name.decode("utf-8")
            full_path = f"{prefix}/{decoded_name}" if prefix else decoded_name

            obj = repo[sha]
            if isinstance(obj, Tree):
                # Recurse into subdirectory
                files.update(self._collect_tree_files(obj, repo, full_path))
            else:
                # It's a file (blob)
                files.add(full_path)

        return files

    def restore_checkpoint(self, commit_id: str) -> list[str]:
        """Restore project files to a specific checkpoint.

        Best-effort restore: skips files that cannot be written (e.g., in use).
        Deletes files that exist in HEAD checkpoint but not in target checkpoint.

        Uses standard git semantics: diff HEAD vs target, delete added files.

        Uses pure dulwich API for all operations - git binary not required.

        Returns:
            List of file paths that were restored (relative to project root)
        """
        repo = self.ensure_repo()

        # Get target checkpoint tree
        target_commit = repo[commit_id.encode()]
        target_tree_id = getattr(target_commit, "tree", None)
        if target_tree_id is None:
            return []
        target_tree = cast(Tree, repo[target_tree_id])
        target_files = self._collect_tree_files(target_tree, repo)

        # Get HEAD checkpoint tree (current state)
        head_files: set[str] = set()
        try:
            active_session = self._get_active_session_name()
            session_ref = self._get_session_ref(active_session)
            if session_ref in repo.refs:
                head_commit = repo[repo.refs[session_ref]]
            else:
                head_commit = repo[repo.head()]

            head_tree_id = getattr(head_commit, "tree", None)
            if head_tree_id:
                head_tree = cast(Tree, repo[head_tree_id])
                head_files = self._collect_tree_files(head_tree, repo)
        except Exception:
            # No HEAD commit yet or error - nothing to delete
            head_files = set()

        # Also include staged files (in index) - these are uncommitted but agent-created
        # They should be deleted if not in target checkpoint
        try:
            index = repo.open_index()
            for path, _entry in index.items():
                head_files.add(path.decode("utf-8"))
        except (FileNotFoundError, OSError):
            # No index - nothing staged
            pass

        # Standard git diff: files in HEAD (+ staged) but not in target = files to delete
        deleted_count = 0
        files_to_delete = head_files - target_files

        for file_path_str in files_to_delete:
            target = self.project_root / file_path_str
            try:
                if target.exists():
                    target.unlink()
                    deleted_count += 1
            except (OSError, PermissionError):
                # Skip files that cannot be deleted
                pass

        # Clean up empty directories left after file deletion
        # Walk bottom-up so we delete child dirs before parents
        for root, dirs, _files in os.walk(self.project_root, topdown=False):
            for dir_name in dirs:
                dir_path = Path(root) / dir_name
                try:
                    # Only delete if empty (no files, no subdirs)
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                except (OSError, PermissionError, ValueError):
                    # Skip dirs that cannot be deleted or are outside project root
                    pass

        # Now restore files from checkpoint
        restored_count = 0
        skipped_count = 0
        restored_files: list[str] = []

        def restore_tree(tree_obj: Tree, path_prefix: str = "") -> None:
            nonlocal restored_count, skipped_count

            for name, _mode, sha in tree_obj.items():
                decoded_name = name.decode("utf-8")
                full_path = (
                    f"{path_prefix}/{decoded_name}" if path_prefix else decoded_name
                )

                obj = repo[sha]
                # Check if it's a subtree (directory)
                if isinstance(obj, Tree):
                    restore_tree(obj, full_path)
                else:
                    # It's a blob (file)
                    data = getattr(obj, "data", None)
                    if data is not None:
                        target = self.project_root / full_path
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(data)
                            restored_count += 1
                            restored_files.append(full_path)
                        except (OSError, PermissionError) as e:
                            # Skip files that cannot be written (in use, permission denied, etc)
                            skipped_count += 1
                            from agentsmithy.utils.logger import agent_logger

                            agent_logger.debug(
                                "Skipped file during restore (in use or no permission)",
                                file=str(target),
                                error=str(e),
                            )

        restore_tree(target_tree)

        # Clear staging area after restore
        # Staged files were either deleted (not in target) or will be committed later
        self.clear_staging()

        from agentsmithy.utils.logger import agent_logger

        agent_logger.info(
            "Checkpoint restore completed",
            commit_id=commit_id[:8],
            restored=restored_count,
            deleted=deleted_count,
            skipped=skipped_count,
        )

        return restored_files

    def _record_metadata(self, commit_id: str, message: str) -> None:
        """Record checkpoint metadata (commit ID and message) to metadata.json.

        Args:
            commit_id: Git commit SHA
            message: Checkpoint message
        """
        meta_file = self.shadow_root / "metadata.json"
        data: dict[str, dict] = {}
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text())
            except Exception:
                data = {}
        data[commit_id] = {"message": message}
        meta_file.write_text(json.dumps(data, indent=2))

    def approve_all(self, message: str | None = None) -> dict:
        """Approve current session by merging into main and creating new session.

        Returns:
            Dict with approved_commit, new_session, commits_approved
        """
        import time

        from dulwich.objects import Commit, parse_timezone

        from agentsmithy.db.sessions import (
            close_session,
            create_new_session,
            update_branch_head,
        )

        repo = self.ensure_repo()

        # First, commit any pending changes before approving
        # - Uncommitted changes in working directory
        # - Or staged entries in the index (force-added files)
        if self.has_uncommitted_changes() or self.has_staged_changes():
            self.create_checkpoint("Auto-commit before approval")
            # Defensive: ensure staging is clear in case of index leftovers
            self.clear_staging()

        # Get current session and main
        active_session = self._get_active_session_name()
        session_ref = self._get_session_ref(active_session)

        if session_ref not in repo.refs or self.MAIN_BRANCH not in repo.refs:
            raise ValueError("Branches not initialized")

        session_head = repo.refs[session_ref]
        main_head = repo.refs[self.MAIN_BRANCH]

        # Check if already same
        if session_head == main_head:
            # Nothing to approve, just create new session
            new_session_num = int(active_session.split("_")[1]) + 1
            new_session = f"session_{new_session_num}"
            self._create_session(new_session, main_head)

            # Update database
            db_path = self._get_db_path()
            close_session(db_path, active_session, "merged", main_head.decode())
            create_new_session(db_path, new_session)

            return {
                "approved_commit": main_head.decode(),
                "new_session": new_session,
                "commits_approved": 0,
            }

        # Create merge commit
        session_commit = repo[session_head]
        merge_msg = message or "✅ Approved session"

        merge_commit = Commit()
        merge_commit.tree = session_commit.tree  # type: ignore[attr-defined]
        merge_commit.parents = [main_head, session_head]  # Two parents for merge
        merge_commit.author = merge_commit.committer = (
            b"AgentSmithy Versioning <versioning@agentsmithy.local>"
        )
        merge_commit.commit_time = merge_commit.author_time = int(time.time())
        merge_commit.commit_timezone = merge_commit.author_timezone = parse_timezone(
            b"+0000"
        )[0]
        merge_commit.message = merge_msg.encode("utf-8")

        # Save merge commit
        repo.object_store.add_object(merge_commit)

        # Update main branch
        repo.refs[self.MAIN_BRANCH] = merge_commit.id

        # Update session branch to merge commit
        repo.refs[session_ref] = merge_commit.id

        # Create new session from main
        new_session_num = int(active_session.split("_")[1]) + 1
        new_session = f"session_{new_session_num}"
        self._create_session(new_session, merge_commit.id)

        # Count commits approved (from main to session before merge)
        commits_approved = self._count_commits_between(repo, main_head, session_head)

        merge_commit_id = merge_commit.id.decode()
        self._record_metadata(merge_commit_id, merge_msg)

        # Update database
        db_path = self._get_db_path()
        close_session(db_path, active_session, "merged", merge_commit_id)
        create_new_session(db_path, new_session)
        update_branch_head(db_path, "main", merge_commit_id)

        # Safety: ensure staging area is cleared after approval
        try:
            index_path = Path(repo.path) / "index"
            if index_path.exists():
                index_path.unlink()
        except Exception:
            # Non-critical: failure to remove index file does not affect approval process
            pass

        return {
            "approved_commit": merge_commit_id,
            "new_session": new_session,
            "commits_approved": commits_approved,
        }

    def reset_to_approved(self) -> dict:
        """Reset current session to approved state (main branch).

        If there are uncommitted or staged changes, creates an automatic checkpoint
        before reset to preserve work. This checkpoint can be restored later if needed.

        Returns:
            Dict with reset_to (commit), new_session, and optional pre_reset_checkpoint
        """
        from agentsmithy.db.sessions import close_session, create_new_session

        repo = self.ensure_repo()

        # Get main branch
        if self.MAIN_BRANCH not in repo.refs:
            raise ValueError("Main branch not initialized")

        main_head = repo.refs[self.MAIN_BRANCH]

        # Get current session
        active_session = self._get_active_session_name()

        # Safety: Create checkpoint if there are uncommitted or staged changes
        pre_reset_checkpoint = None
        if self.has_staged_changes() or self.has_uncommitted_changes():
            from agentsmithy.utils.logger import agent_logger

            try:
                checkpoint = self.create_checkpoint(
                    "Auto-save before reset (can be restored if needed)"
                )
                pre_reset_checkpoint = checkpoint.commit_id

                agent_logger.info(
                    "Created auto-save checkpoint before reset",
                    checkpoint_id=checkpoint.commit_id[:8],
                )
            except Exception as e:
                agent_logger.warning(
                    "Failed to create auto-save checkpoint before reset",
                    error=str(e),
                )
                # Continue with reset even if checkpoint fails

        # Create new session from main
        new_session_num = int(active_session.split("_")[1]) + 1
        new_session = f"session_{new_session_num}"
        self._create_session(new_session, main_head)

        # Update database - mark current session as abandoned
        db_path = self._get_db_path()
        close_session(db_path, active_session, "abandoned")
        create_new_session(db_path, new_session)

        result = {
            "reset_to": main_head.decode(),
            "new_session": new_session,
        }
        if pre_reset_checkpoint:
            result["pre_reset_checkpoint"] = pre_reset_checkpoint

        return result

    def has_staged_changes(self) -> bool:
        """Return True if there are entries in the staging area (index).

        Semantics:
        - stage_file() adds entries to the index
        - create_checkpoint() and restore_checkpoint() clear the index
        Therefore, non-empty index means there are explicit, pending changes
        prepared for the next checkpoint.
        """
        repo = self.ensure_repo()
        try:
            index = repo.open_index()
            # Any entry indicates staged changes
            for _ in index.items():
                return True
            return False
        except (FileNotFoundError, OSError):
            return False

    def clear_staging(self) -> None:
        """Clear staging area (index) entries and remove index file if present."""
        repo = self.ensure_repo()
        try:
            # Try to clear via dulwich API first
            try:
                index = repo.open_index()
                # Remove all entries
                for key in list(index._byname.keys()):
                    try:
                        del index._byname[key]
                    except Exception:
                        # Best-effort: if an index entry cannot be removed, continue clearing others
                        pass
                # Rebuild and write empty index safely
                try:
                    index.write()
                except Exception:
                    # Non-critical: failure to write empty index is acceptable; fallback cleanup follows
                    pass
            except Exception:
                pass

            # Ensure index files are removed
            # Dulwich stores index at .git/index for non-bare repos
            git_dir = Path(repo.path)
            if git_dir.name != ".git":
                git_dir = git_dir / ".git"
            index_path = git_dir / "index"
            lock_path = git_dir / "index.lock"
            if lock_path.exists():
                lock_path.unlink()
            if index_path.exists():
                index_path.unlink()
        except Exception:
            # Best-effort cleanup
            pass

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes in working directory.

        Compares current files on disk with the latest checkpoint in active session.
        Uses optimized mtime+size check first, falls back to content hash only when needed.
        Uses pure dulwich API - git binary not required.
        """
        repo = self.ensure_repo()

        try:
            # Get current session HEAD
            active_session = self._get_active_session_name()
            session_ref = self._get_session_ref(active_session)

            if session_ref not in repo.refs:
                return False

            session_head = repo.refs[session_ref]
            session_commit = repo[session_head]
            committed_tree_id = session_commit.tree  # type: ignore[attr-defined]
            committed_tree = repo[committed_tree_id]

            # Build map of committed files: path -> (mode, sha)
            import os

            committed_files: dict[str, tuple[int, bytes]] = {}

            def collect_tree_entries(tree: Any, prefix: str = "") -> None:
                """Recursively collect all entries from tree."""
                for name, mode, sha in tree.items():
                    decoded_name = name.decode("utf-8")
                    full_path = f"{prefix}/{decoded_name}" if prefix else decoded_name
                    obj = repo[sha]
                    if isinstance(obj, Tree):
                        collect_tree_entries(obj, full_path)
                    else:
                        committed_files[full_path] = (mode, sha)

            collect_tree_entries(committed_tree)

            # Scan working directory and compare
            ignore_spec = self._get_ignore_spec()

            # Filter out committed files that are NOW ignored
            # (to handle case where ignore patterns changed after checkpoint)
            non_ignored_committed = {
                path
                for path in committed_files.keys()
                if not ignore_spec.match_file(path)
            }

            current_files: set[str] = set()

            for root, dirs, files in os.walk(self.project_root):
                root_path = Path(root)
                rel_root = (
                    root_path.relative_to(self.project_root)
                    if root_path != self.project_root
                    else Path(".")
                )

                # Filter directories
                filtered_dirs = []
                for d in dirs:
                    dir_rel_path = (rel_root / d) if rel_root != Path(".") else Path(d)
                    dir_path_str = str(dir_rel_path).replace("\\", "/")
                    if ignore_spec.match_file(dir_path_str):
                        continue
                    filtered_dirs.append(d)

                dirs[:] = filtered_dirs

                for filename in files:
                    file_path = Path(root) / filename
                    file_rel_path = file_path.relative_to(self.project_root)
                    file_path_str = str(file_rel_path).replace("\\", "/")

                    if ignore_spec.match_file(file_path_str):
                        continue

                    try:
                        current_files.add(file_path_str)

                        # Check if file exists in commit (among non-ignored files)
                        if file_path_str not in non_ignored_committed:
                            # New file - uncommitted change
                            return True

                        _mode, committed_sha = committed_files[file_path_str]
                        committed_blob = repo[committed_sha]

                        # Fast check: compare sizes first (avoids reading file content)
                        stat = file_path.stat()
                        file_size = stat.st_size
                        blob_data = getattr(committed_blob, "data", b"")
                        blob_size = len(blob_data)

                        if file_size != blob_size:
                            # Size mismatch - file changed
                            return True

                        # Sizes match, but we need to check content hash to be sure
                        # (size collision is possible but rare)
                        from dulwich.objects import Blob

                        content = file_path.read_bytes()
                        current_blob = Blob.from_string(content)

                        if current_blob.id != committed_sha:
                            # Content hash mismatch - file changed
                            return True

                    except Exception:
                        # If we can't read file, assume no change
                        continue

            # Check if any non-ignored committed files were deleted
            # (only check files that are not now ignored by current patterns)
            deleted_files = non_ignored_committed - current_files
            if deleted_files:
                return True

            return False

        except Exception:
            return False

    def _count_commits_between(
        self, repo: Repo, base_sha: bytes, head_sha: bytes
    ) -> int:
        """Count commits between base and head (exclusive of base, inclusive of head).

        Uses BFS traversal with deque for O(1) queue operations.
        """
        if base_sha == head_sha:
            return 0

        # Collect commits from head to base using BFS
        count = 0
        visited = set()
        to_visit = deque([head_sha])

        while to_visit:
            sha = to_visit.popleft()
            if sha in visited or sha == base_sha:
                continue
            visited.add(sha)
            count += 1

            try:
                commit = repo[sha]
                parents = getattr(commit, "parents", [])
                to_visit.extend(parents)
            except Exception:
                continue

        return count

    def list_checkpoints(self) -> list[CheckpointInfo]:
        """List all checkpoints in chronological order (oldest first).

        Uses pure dulwich API - git binary not required.
        Uses BFS traversal with deque for O(1) queue operations.

        Returns:
            List of CheckpointInfo objects from active session
        """
        try:
            repo = self.ensure_repo()
            checkpoints: list[CheckpointInfo] = []

            # Read metadata for messages
            meta_file = self.shadow_root / "metadata.json"
            metadata: dict[str, dict] = {}
            if meta_file.exists():
                try:
                    metadata = json.loads(meta_file.read_text())
                except Exception:
                    # Non-critical: corrupted or unreadable metadata file is treated as empty.
                    # This allows recovery from malformed JSON without blocking checkpoint restore.
                    metadata = {}

            # Get active session branch (not HEAD which might be on different branch)
            active_session = self._get_active_session_name()
            session_ref = self._get_session_ref(active_session)

            # Walk commit history from active session backwards using BFS
            try:
                if session_ref in repo.refs:
                    current_id = repo.refs[session_ref]
                else:
                    # Fallback to HEAD if session doesn't exist yet
                    current_id = repo.head()
            except Exception:
                # No commits yet
                return []

            visited = set()
            to_visit = deque([current_id])

            while to_visit:
                commit_id = to_visit.popleft()
                if commit_id in visited:
                    continue
                visited.add(commit_id)

                try:
                    commit_obj = repo[commit_id]
                    commit_id_str = commit_id.decode("utf-8")

                    # Get message from metadata or commit
                    if commit_id_str in metadata:
                        message = metadata[commit_id_str].get("message", "")
                    else:
                        message = getattr(commit_obj, "message", b"").decode("utf-8")

                    checkpoints.append(
                        CheckpointInfo(commit_id=commit_id_str, message=message)
                    )

                    # Add parents to visit
                    parents = getattr(commit_obj, "parents", [])
                    to_visit.extend(parents)
                except Exception:
                    continue

            # Reverse to get chronological order (oldest first)
            checkpoints.reverse()
            return checkpoints

        except Exception:
            return []

    def get_tree_diff(
        self, from_ref: bytes | str, to_ref: bytes | str
    ) -> list[dict[str, Any]]:
        """Get diff between two refs/commits with file statistics.

        Args:
            from_ref: Source ref (e.g. b"refs/heads/main" or "main")
            to_ref: Target ref (e.g. b"refs/heads/session_1" or "session_1")

        Returns:
            List of dicts with keys: path, status, additions, deletions
            Status can be: 'added', 'modified', 'deleted'
        """
        repo = self.ensure_repo()

        try:
            # Normalize refs
            if isinstance(from_ref, str):
                if not from_ref.startswith("refs/"):
                    from_ref = f"refs/heads/{from_ref}"
                from_ref = from_ref.encode()
            if isinstance(to_ref, str):
                if not to_ref.startswith("refs/"):
                    to_ref = f"refs/heads/{to_ref}"
                to_ref = to_ref.encode()

            # Check if refs exist
            if from_ref not in repo.refs or to_ref not in repo.refs:
                return []

            # Get commit objects
            from_commit = repo[repo.refs[from_ref]]
            to_commit = repo[repo.refs[to_ref]]

            # Get trees
            from_tree_id = getattr(from_commit, "tree", None)
            to_tree_id = getattr(to_commit, "tree", None)

            if not from_tree_id or not to_tree_id:
                return []

            from_tree = repo[from_tree_id]
            to_tree = repo[to_tree_id]

            # Collect files from both trees
            from_files: dict[str, bytes] = {}  # path -> blob sha
            to_files: dict[str, bytes] = {}  # path -> blob sha

            def collect_blobs(tree: Tree, prefix: str = "") -> dict[str, bytes]:
                """Recursively collect all blobs from tree."""
                blobs: dict[str, bytes] = {}
                for name, _mode, sha in tree.items():
                    decoded_name = name.decode("utf-8")
                    full_path = f"{prefix}/{decoded_name}" if prefix else decoded_name
                    obj = repo[sha]
                    if isinstance(obj, Tree):
                        blobs.update(collect_blobs(obj, full_path))
                    else:
                        blobs[full_path] = sha
                return blobs

            from_files = collect_blobs(cast(Tree, from_tree))
            to_files = collect_blobs(cast(Tree, to_tree))

            # Calculate diff
            all_paths = set(from_files.keys()) | set(to_files.keys())
            changes: list[dict[str, Any]] = []

            for path in sorted(all_paths):
                from_sha = from_files.get(path)
                to_sha = to_files.get(path)

                if from_sha == to_sha:
                    continue  # No change

                if not from_sha:
                    # File added
                    additions, deletions = self._count_lines(repo, to_sha)
                    changes.append(
                        {
                            "path": path,
                            "status": "added",
                            "additions": additions,
                            "deletions": 0,
                        }
                    )
                elif not to_sha:
                    # File deleted
                    additions, deletions = self._count_lines(repo, from_sha)
                    changes.append(
                        {
                            "path": path,
                            "status": "deleted",
                            "additions": 0,
                            "deletions": deletions,
                        }
                    )
                else:
                    # File modified - calculate line diff
                    additions, deletions = self._diff_blobs(repo, from_sha, to_sha)
                    changes.append(
                        {
                            "path": path,
                            "status": "modified",
                            "additions": additions,
                            "deletions": deletions,
                        }
                    )

            return changes

        except Exception:
            return []

    def _count_lines(self, repo: Repo, blob_sha: bytes | None) -> tuple[int, int]:
        """Count lines in a blob (for additions/deletions of new/deleted files).

        Returns:
            Tuple of (additions, deletions) - one will be 0
        """
        if not blob_sha:
            return (0, 0)

        try:
            from dulwich.objects import Blob

            blob_obj = repo[blob_sha]
            if not isinstance(blob_obj, Blob):
                return (0, 0)
            content = blob_obj.data
            # Check if binary
            if b"\x00" in content[:8192]:
                return (0, 0)  # Binary file
            lines = content.count(b"\n")
            return (lines, 0)
        except Exception:
            return (0, 0)

    def _diff_blobs(
        self, repo: Repo, from_sha: bytes, to_sha: bytes
    ) -> tuple[int, int]:
        """Calculate additions/deletions between two blobs.

        Returns:
            Tuple of (additions, deletions)
        """
        try:
            from dulwich.objects import Blob

            from_blob_obj = repo[from_sha]
            to_blob_obj = repo[to_sha]

            if not isinstance(from_blob_obj, Blob) or not isinstance(to_blob_obj, Blob):
                return (0, 0)

            from_content = from_blob_obj.data
            to_content = to_blob_obj.data

            # Check if binary
            if b"\x00" in from_content[:8192] or b"\x00" in to_content[:8192]:
                return (0, 0)  # Binary file

            # Simple line-based diff
            from_lines = from_content.splitlines(keepends=False)
            to_lines = to_content.splitlines(keepends=False)

            # Use simple heuristic: count unique lines
            from_set = set(from_lines)
            to_set = set(to_lines)

            # Lines only in 'to' are additions
            additions = len([line for line in to_lines if line not in from_set])
            # Lines only in 'from' are deletions
            deletions = len([line for line in from_lines if line not in to_set])

            return (additions, deletions)

        except Exception:
            return (0, 0)
