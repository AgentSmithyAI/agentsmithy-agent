from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from dulwich import porcelain
from dulwich.objects import Blob, Commit, Tree  # precise types for object store
from dulwich.repo import Repo

DEFAULT_EXCLUDES = [
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "node_modules/",
    "chroma_db/",
    ".agentsmithy/",
    "dist/",
    "build/",
    "target/",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
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
    for pattern in patterns:
        # Directory patterns (ending with /)
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            # Match if path starts with directory or IS the directory
            if path_str == dir_pattern or path_str.startswith(dir_pattern + "/"):
                return True
        # Glob patterns (with * or ?)
        elif "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(path_str, pattern):
                return True
            # Also check with leading **/
            if fnmatch.fnmatch(path_str, f"**/{pattern}"):
                return True
        # Exact match
        else:
            if path_str == pattern or path_str.startswith(pattern + "/"):
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
        repo = self.ensure_repo()

        # Since we have a non-bare repo, we need to add files from the project directory
        # We'll create blob objects directly and build the tree
        import os
        import time

        from dulwich.objects import Blob, Commit, Tree, parse_timezone

        # Get current tree from active session (not HEAD which might point to wrong branch)
        active_session = self._get_active_session_name()
        session_ref = self._get_session_ref(active_session)

        parent_commit = None
        try:
            if session_ref in repo.refs:
                session_head = repo.refs[session_ref]
                parent_commit = repo[session_head]
            else:
                # Fallback to HEAD if session doesn't exist
                parent_commit = repo[repo.head()]
        except Exception:
            parent_commit = None

        # Create new tree by scanning project directory
        tree: Tree = Tree()

        # Load .gitignore patterns
        gitignore = self.project_root / ".gitignore"
        ignore_patterns = _load_gitignore_patterns(gitignore)

        # Walk through project directory and add files
        for root, dirs, files in os.walk(self.project_root):
            # Convert to relative path for ignore check
            root_path = Path(root)
            rel_root = (
                root_path.relative_to(self.project_root)
                if root_path != self.project_root
                else Path(".")
            )

            # Filter directories using ignore patterns
            filtered_dirs = []
            for d in dirs:
                dir_rel_path = (rel_root / d) if rel_root != Path(".") else Path(d)
                dir_path_str = str(dir_rel_path).replace("\\", "/")

                # Check if directory should be ignored
                if _is_ignored(dir_path_str, ignore_patterns):
                    continue

                # Also apply hardcoded excludes
                if d.startswith(".") or d in [
                    "node_modules",
                    "__pycache__",
                    "dist",
                    "build",
                    "target",
                ]:
                    continue

                filtered_dirs.append(d)

            # Update dirs in-place to control recursion
            dirs[:] = filtered_dirs

            for filename in files:
                # Skip hidden files and common artifacts
                if (
                    filename.startswith(".")
                    or filename.endswith(".pyc")
                    or filename.endswith(".pyo")
                    or filename.endswith(".so")
                    or filename.endswith(".dylib")
                    or filename.endswith(".dll")
                ):
                    continue

                file_path = Path(root) / filename

                # Check if file should be ignored
                file_rel_path = file_path.relative_to(self.project_root)
                file_path_str = str(file_rel_path).replace("\\", "/")
                if _is_ignored(file_path_str, ignore_patterns):
                    continue

                try:
                    # Read file content
                    content = file_path.read_bytes()

                    # Create blob
                    blob: Blob = Blob.from_string(content)
                    repo.object_store.add_object(blob)

                    # Add to tree with relative path
                    tree_path = file_path_str.encode("utf-8")
                    tree.add(tree_path, 0o100644, blob.id)

                except Exception:
                    # Skip files we can't read
                    continue

        # Allow empty commits (needed for initial checkpoint of empty projects)
        # Add tree to repo (even if empty)
        repo.object_store.add_object(tree)

        # Create commit
        commit: Commit = Commit()
        commit.tree = tree.id
        if parent_commit:
            commit.parents = [parent_commit.id]
        else:
            commit.parents = []

        commit.author = commit.committer = (
            b"AgentSmithy Versioning <versioning@agentsmithy.local>"
        )
        commit.commit_time = commit.author_time = int(time.time())
        commit.commit_timezone = commit.author_timezone = parse_timezone(b"+0000")[0]
        commit.message = message.encode("utf-8")

        # Add commit to repo
        repo.object_store.add_object(commit)

        # Update active session branch directly (ignore HEAD which may be on wrong branch)
        active_session = self._get_active_session_name()
        session_ref = self._get_session_ref(active_session)
        repo.refs[session_ref] = commit.id

        # If this is first commit (no parents), also initialize main branch
        if not commit.parents and self.MAIN_BRANCH not in repo.refs:
            repo.refs[self.MAIN_BRANCH] = commit.id

        commit_id = commit.id.decode("utf-8")
        self._record_metadata(commit_id, message)
        return CheckpointInfo(commit_id=commit_id, message=message)

    def restore_checkpoint(self, commit_id: str) -> list[str]:
        """Restore project files to a specific checkpoint.

        Best-effort restore: skips files that cannot be written (e.g., in use).

        Returns:
            List of file paths that were restored (relative to project root)
        """
        repo = self.ensure_repo()
        # Checkout the given tree into worktree by reading blobs and writing files
        # mypy: dulwich types use dynamic attributes; guard with isinstance checks
        commit_obj = repo[commit_id.encode()]
        tree_id = getattr(commit_obj, "tree", None)
        if tree_id is None:
            return []
        tree = cast(Tree, repo[tree_id])

        # Recursively walk tree and restore files
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
