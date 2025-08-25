from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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

    - Shadow repo path: ~/.agentsmithy/checkpoints/{cwd_hash}/.git
    - Worktree points to real project directory
    - Only used to create checkpoints and restore files
    - Does not touch user's main .git in the project
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root).resolve()
        self.cwd_hash = stable_hash(str(self.project_root))
        self.shadow_root = Path(os.path.expanduser("~/.agentsmithy/checkpoints")) / self.cwd_hash
        self.shadow_root.mkdir(parents=True, exist_ok=True)
        self.repo_path = self.shadow_root / ".git"
        self._tmp_dir: Path | None = None
        self._preedit_snapshots: dict[Path, bytes] = {}

    # ---- repo management ----
    def ensure_repo(self) -> Repo:
        if self.repo_path.exists():
            repo = Repo(str(self.repo_path))
        else:
            repo = porcelain.init(path=str(self.shadow_root), bare=True)
        # Set core.worktree so porcelain works over project files
        with repo.get_config() as cfg:
            cfg.set((b"core",), b"worktree", bytes(str(self.project_root), "utf-8"))
            cfg.set((b"user",), b"name", b"AgentSmithy Versioning")
            cfg.set((b"user",), b"email", b"versioning@agentsmithy.local")
        # Ensure initial commit exists
        try:
            _ = repo.head()
        except Exception:
            try:
                porcelain.commit(repo, b"initial")
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
            patterns.extend([line.strip() for line in gitignore.read_text().splitlines() if line.strip()])
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
        try:
            porcelain.add(repo, paths=["."])
        except Exception:
            pass
        try:
            commit_bytes = porcelain.commit(repo, bytes(message, "utf-8"))
            commit_id = commit_bytes.decode() if isinstance(commit_bytes, (bytes, bytearray)) else str(commit_bytes)
            self._record_metadata(commit_id, message)
            return CheckpointInfo(commit_id=commit_id, message=message)
        except Exception:
            # If commit fails (no changes), return last HEAD if available
            try:
                head = repo.head().decode()
            except Exception:
                head = ""
            return CheckpointInfo(commit_id=head, message=message)

    def restore_checkpoint(self, commit_id: str) -> None:
        repo = self.ensure_repo()
        # Checkout the given tree into worktree by reading blobs and writing files
        tree = repo[repo[commit_id.encode()].tree]
        # Build index of all blobs in target commit
        for entry in tree.walk():
            _, _, files = entry
            for name, mode, sha in files:
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


