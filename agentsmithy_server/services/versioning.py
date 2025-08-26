from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dulwich import porcelain
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
        tree = Tree()

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
                    blob = Blob.from_string(content)
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
        commit = Commit()
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
        tree = repo[repo[commit_id.encode()].tree]
        # Build index of all blobs in target commit
        for entry in tree.walk():
            _, _, files = entry
            for name, _mode, sha in files:
                rel = Path(name.decode())
                target = self.project_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                data = repo[sha].data
                target.write_bytes(data)

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
