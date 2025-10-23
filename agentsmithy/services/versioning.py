from __future__ import annotations

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
]


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:13]


@dataclass
class CheckpointInfo:
    commit_id: str
    message: str


class VersioningTracker:
    """Shadow-repo versioning isolated from project's own Git.

    - Each dialog has its own repo: {project_root}/.agentsmithy/dialogs/{dialog_id}/checkpoints/
    - Uses non-bare repository to track project files
    - Only used to create checkpoints and restore files
    - Does not touch user's main .git in the project
    """

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

        # Ensure initial commit exists
        try:
            _ = repo.head()
        except Exception:
            try:
                # Create empty initial commit
                porcelain.commit(repo, b"Initial checkpoint")
            except Exception:
                pass

        self._write_excludes(repo)
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

    # ---- checkpoints ----
    def create_checkpoint(self, message: str) -> CheckpointInfo:
        repo = self.ensure_repo()

        # Since we have a non-bare repo, we need to add files from the project directory
        # We'll create blob objects directly and build the tree
        import os
        import time

        from dulwich.objects import Blob, Commit, Tree, parse_timezone

        # Get current tree (if exists)
        try:
            parent_commit = repo[repo.head()]
        except Exception:
            parent_commit = None

        # Create new tree by scanning project directory
        tree: Tree = Tree()

        # Walk through project directory and add files
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden directories and common build artifacts
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["node_modules", "__pycache__", "venv", ".venv"]
            ]

            for filename in files:
                # Skip hidden files and common artifacts
                if filename.startswith(".") or filename.endswith(".pyc"):
                    continue

                file_path = Path(root) / filename
                try:
                    # Read file content
                    content = file_path.read_bytes()

                    # Create blob
                    blob: Blob = Blob.from_string(content)
                    repo.object_store.add_object(blob)

                    # Add to tree with relative path
                    rel_path = file_path.relative_to(self.project_root)
                    tree_path = str(rel_path).replace("\\", "/").encode("utf-8")
                    tree.add(tree_path, 0o100644, blob.id)

                except Exception:
                    # Skip files we can't read
                    continue

        # Only create commit if tree has entries
        if len(tree) == 0:
            # No files to track, return current HEAD
            try:
                head = repo.head().decode("utf-8")
            except Exception:
                head = ""
            return CheckpointInfo(commit_id=head, message=message)

        # Add tree to repo
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

        # Update HEAD
        repo.refs[b"HEAD"] = commit.id

        commit_id = commit.id.decode("utf-8")
        self._record_metadata(commit_id, message)
        return CheckpointInfo(commit_id=commit_id, message=message)

    def restore_checkpoint(self, commit_id: str) -> None:
        repo = self.ensure_repo()
        # Checkout the given tree into worktree by reading blobs and writing files
        # mypy: dulwich types use dynamic attributes; guard with isinstance checks
        commit_obj = repo[commit_id.encode()]
        tree_id = getattr(commit_obj, "tree", None)
        if tree_id is None:
            return
        tree = cast(Tree, repo[tree_id])

        # Recursively walk tree and restore files
        def restore_tree(tree_obj: Tree, path_prefix: str = "") -> None:
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
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)

        restore_tree(tree)

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

    def list_checkpoints(self) -> list[CheckpointInfo]:
        """List all checkpoints in chronological order (oldest first).

        Returns:
            List of CheckpointInfo objects
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

            # Walk commit history from HEAD backwards
            try:
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
