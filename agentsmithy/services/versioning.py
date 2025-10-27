from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dulwich import porcelain
from dulwich.objects import Commit, Tree  # precise types for object store
from dulwich.repo import Repo

# Note: This module uses dulwich (pure Python git implementation) for all git operations.
# Git binary is not required - everything works through dulwich API.

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
    "htmlcov/",
    "*.egg-info/",
    "dist/",
    "build/",
    ".eggs/",
    # Node.js / JavaScript / TypeScript
    "node_modules/",
    ".npm/",
    ".yarn/",
    "npm-debug.log*",
    "yarn-error.log*",
    ".next/",
    ".nuxt/",
    "out/",
    ".cache/",
    # Java / Kotlin / Scala
    "target/",
    ".gradle/",
    ".m2/",
    "*.class",
    "*.jar",
    "*.war",
    "*.ear",
    # C / C++
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
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    # Logs
    "*.log",
    "logs/",
    # Temporary files
    "tmp/",
    "temp/",
    "*.tmp",
    "*.bak",
    "*.swp",
    "*.swo",
    "*~",
]


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:13]


def _load_gitignore_patterns(gitignore_path: Path) -> list[str]:
    """Load and parse .gitignore patterns.

    Returns list of patterns suitable for fnmatch.
    """
    if not gitignore_path.exists():
        return []

    patterns = []
    for line in gitignore_path.read_text().splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue
        patterns.append(line)

    return patterns


def _is_ignored(path_str: str, patterns: list[str]) -> bool:
    """Check if a path matches any gitignore pattern.

    Args:
        path_str: Relative path as string (e.g., "src/main.py" or "dist")
        patterns: List of gitignore patterns

    Returns:
        True if path should be ignored
    """
    # Split path into parts for matching
    path_parts = path_str.split("/")
    filename = path_parts[-1] if path_parts else path_str

    for pattern in patterns:
        # Directory patterns (ending with /)
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            # Match if path starts with directory or IS the directory
            if path_str == dir_pattern or path_str.startswith(dir_pattern + "/"):
                return True
            # Also check if directory name appears anywhere in path
            if dir_pattern in path_parts:
                return True

        # Glob patterns (with * or ?)
        elif "*" in pattern or "?" in pattern:
            # Extension patterns like *.pyc
            if pattern.startswith("*."):
                if fnmatch.fnmatch(filename, pattern):
                    return True
            # Patterns with ** (match anywhere)
            elif "**/" in pattern:
                suffix = pattern.replace("**/", "")
                if fnmatch.fnmatch(path_str, f"*/{suffix}") or fnmatch.fnmatch(
                    path_str, suffix
                ):
                    return True
            # cmake-build-* style patterns
            elif pattern.endswith("*") or pattern.endswith("*/"):
                base_pattern = pattern.rstrip("*/")
                # Check each path component
                for part in path_parts:
                    if fnmatch.fnmatch(part, base_pattern + "*"):
                        return True
            # Regular glob
            else:
                if fnmatch.fnmatch(path_str, pattern):
                    return True
                # Also check filename only
                if fnmatch.fnmatch(filename, pattern):
                    return True

        # Exact match
        else:
            if path_str == pattern or path_str.startswith(pattern + "/"):
                return True
            # Check if exact name appears as directory in path
            if pattern in path_parts:
                return True

    return False


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
        self._preedit_snapshots.clear()
        for p in paths:
            abs_path = (self.project_root / p).resolve()
            if abs_path.is_file():
                self._preedit_snapshots[abs_path] = abs_path.read_bytes()
        if self._preedit_snapshots:
            self._tmp_dir = Path(tempfile.mkdtemp(prefix="asm_preedit_"))

    def abort_edit(self) -> None:
        for abs_path, content in self._preedit_snapshots.items():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(content)
        self._cleanup_edit()

    def finalize_edit(self) -> None:
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

    def _get_tracked_files_path(self) -> Path:
        """Get path to tracked files metadata."""
        return self.shadow_root.parent / "tracked_files.json"

    def _load_tracked_files(self) -> set[str]:
        """Load set of files tracked by agent."""
        tracked_path = self._get_tracked_files_path()
        if not tracked_path.exists():
            return set()
        try:
            data = json.loads(tracked_path.read_text())
            return set(data.get("files", []))
        except Exception:
            return set()

    def _save_tracked_files(self, files: set[str]) -> None:
        """Save set of tracked files."""
        tracked_path = self._get_tracked_files_path()
        tracked_path.parent.mkdir(parents=True, exist_ok=True)
        tracked_path.write_text(json.dumps({"files": sorted(files)}, indent=2))

    def stage_file(self, file_path: str) -> None:
        """Mark file as tracked by agent (will be deleted on restore if not in target).

        Args:
            file_path: Path to file relative to project root
        """
        try:
            tracked = self._load_tracked_files()
            tracked.add(file_path)
            self._save_tracked_files(tracked)
        except Exception as e:
            # Best effort - don't fail if tracking fails
            from agentsmithy.utils.logger import agent_logger

            agent_logger.debug("Failed to track file", file=file_path, error=str(e))

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
    def _get_ignore_patterns(self) -> list[str]:
        """Load and merge gitignore patterns with defaults."""
        gitignore = self.project_root / ".gitignore"
        patterns = _load_gitignore_patterns(gitignore)
        patterns.extend(DEFAULT_EXCLUDES)
        return patterns

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
                # Check if file unchanged (by size for quick check)
                existing_blob = project_git_repo[existing_blob_sha]
                file_size = file_path.stat().st_size
                if len(existing_blob.data) == file_size:
                    # File likely unchanged, reuse blob (no file read!)
                    return existing_blob
        except (KeyError, FileNotFoundError, AttributeError):
            # File not in project git or lookup failed
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
        ignore_patterns: list[str],
        project_git_repo: Any,
        project_git_tree: Any,
    ) -> tuple[Any, int, int]:
        """Build git tree by scanning project working directory.

        Uses parallel file processing for better performance with many files.

        Args:
            repo: Shadow repository
            ignore_patterns: List of ignore patterns
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

                if not _is_ignored(dir_path_str, ignore_patterns):
                    filtered_dirs.append(d)

            dirs[:] = filtered_dirs

            # Collect files for parallel processing
            for filename in files:
                file_path = Path(root) / filename
                file_rel_path = file_path.relative_to(self.project_root)
                file_path_str = str(file_rel_path).replace("\\", "/")

                if not _is_ignored(file_path_str, ignore_patterns):
                    files_to_process.append((file_path, file_path_str))

        # Process files in parallel with thread pool
        blobs_to_add: list[Any] = []

        def process_file(file_info: tuple[Path, str]) -> tuple[Any, str, bool] | None:
            """Process single file and return (blob, path, was_reused)."""
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
            except Exception:
                return None

        # Use thread pool for I/O parallelism
        max_workers = min(32, (len(files_to_process) or 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(process_file, file_info)
                for file_info in files_to_process
            ]

            for future in as_completed(futures):
                result = future.result()
                if result:
                    blob, file_path_str, was_reused = result
                    blobs_to_add.append(blob)

                    if was_reused:
                        blobs_reused += 1
                    else:
                        blobs_created += 1

                    # Add to tree
                    tree_path = file_path_str.encode("utf-8")
                    tree.add(tree_path, 0o100644, blob.id)

        # Batch add all blobs to object store
        if blobs_to_add:
            repo.object_store.add_objects([(blob, None) for blob in blobs_to_add])

        return tree, blobs_reused, blobs_created

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

        # Load ignore patterns
        ignore_patterns = self._get_ignore_patterns()

        # Try to open project git for blob reuse optimization
        project_git_repo, project_git_tree = self._open_project_git()

        # Build tree by scanning working directory
        tree, blobs_reused, blobs_created = self._build_tree_from_workdir(
            repo, ignore_patterns, project_git_repo, project_git_tree
        )

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
        repo.refs[session_ref] = commit.id

        # Initialize main branch if this is first commit
        if not commit.parents and self.MAIN_BRANCH not in repo.refs:
            repo.refs[self.MAIN_BRANCH] = commit.id

        # Record metadata
        commit_id = commit.id.decode("utf-8")
        self._record_metadata(commit_id, message)
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
        Deletes files tracked by agent but not in target checkpoint.

        Uses pure dulwich API for all operations - git binary not required.

        Returns:
            List of file paths that were restored (relative to project root)
        """
        repo = self.ensure_repo()

        # Get tree from commit (dulwich API)
        commit_obj = repo[commit_id.encode()]
        tree_id = getattr(commit_obj, "tree", None)
        if tree_id is None:
            return []
        tree = cast(Tree, repo[tree_id])

        # Collect all files from checkpoint tree (pure dulwich - no subprocess!)
        checkpoint_files = self._collect_tree_files(tree, repo)

        # Get files tracked by agent (from tracked_files.json metadata)
        # Only delete files that agent touched
        tracked_files = self._load_tracked_files()

        # Delete only files that were tracked in HEAD but not in target checkpoint
        # This way we don't delete user's manually created files
        deleted_count = 0
        files_to_delete = tracked_files - checkpoint_files

        for file_path_str in files_to_delete:
            target = self.project_root / file_path_str
            try:
                if target.exists():
                    target.unlink()
                    deleted_count += 1
            except (OSError, PermissionError):
                # Skip files that cannot be deleted
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

        restore_tree(tree)

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

        # First, commit any uncommitted changes before approving
        if self.has_uncommitted_changes():
            self.create_checkpoint("Auto-commit before approval")

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

        return {
            "approved_commit": merge_commit_id,
            "new_session": new_session,
            "commits_approved": commits_approved,
        }

    def reset_to_approved(self) -> dict:
        """Reset current session to approved state (main branch).

        Returns:
            Dict with reset_to (commit), new_session
        """
        from agentsmithy.db.sessions import close_session, create_new_session

        repo = self.ensure_repo()

        # Get main branch
        if self.MAIN_BRANCH not in repo.refs:
            raise ValueError("Main branch not initialized")

        main_head = repo.refs[self.MAIN_BRANCH]

        # Get current session
        active_session = self._get_active_session_name()

        # Create new session from main
        new_session_num = int(active_session.split("_")[1]) + 1
        new_session = f"session_{new_session_num}"
        self._create_session(new_session, main_head)

        # Update database - mark current session as abandoned
        db_path = self._get_db_path()
        close_session(db_path, active_session, "abandoned")
        create_new_session(db_path, new_session)

        return {"reset_to": main_head.decode(), "new_session": new_session}

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes in working directory.

        Compares current files on disk with the latest checkpoint in active session.
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

            # Build tree from current working directory
            import os

            from dulwich.objects import Blob, Tree

            current_tree = Tree()
            gitignore = self.project_root / ".gitignore"
            ignore_patterns = _load_gitignore_patterns(gitignore)
            ignore_patterns.extend(DEFAULT_EXCLUDES)

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
                    # Check if directory should be ignored (includes DEFAULT_EXCLUDES + .gitignore)
                    if _is_ignored(dir_path_str, ignore_patterns):
                        continue
                    filtered_dirs.append(d)

                dirs[:] = filtered_dirs

                for filename in files:
                    file_path = Path(root) / filename
                    file_rel_path = file_path.relative_to(self.project_root)
                    file_path_str = str(file_rel_path).replace("\\", "/")

                    # Check if file should be ignored (includes DEFAULT_EXCLUDES + .gitignore)
                    if _is_ignored(file_path_str, ignore_patterns):
                        continue

                    try:
                        content = file_path.read_bytes()
                        blob = Blob.from_string(content)
                        current_tree.add(
                            file_path_str.encode("utf-8"), 0o100644, blob.id
                        )
                    except Exception:
                        continue

            # Compare tree IDs
            return committed_tree_id != current_tree.id

        except Exception:
            return False

    def _count_commits_between(
        self, repo: Repo, base_sha: bytes, head_sha: bytes
    ) -> int:
        """Count commits between base and head (exclusive of base, inclusive of head)."""
        if base_sha == head_sha:
            return 0

        # Collect commits from head to base
        count = 0
        visited = set()
        to_visit = [head_sha]

        while to_visit:
            sha = to_visit.pop(0)
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
                    pass

            # Get active session branch (not HEAD which might be on different branch)
            active_session = self._get_active_session_name()
            session_ref = self._get_session_ref(active_session)

            # Walk commit history from active session backwards
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
            to_visit = [current_id]

            while to_visit:
                commit_id = to_visit.pop(0)
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
