"""Project and workspace management.

This module defines an extensible Project entity and a ProjectWorkspace that
own directory-related concerns. It is designed to be expanded with metadata,
configuration, indexing, and other project-level behaviors.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentsmithy.dialogs.history import DialogHistory
from agentsmithy.utils.logger import get_logger

logger = get_logger("project")


@dataclass
class Project:
    """Represents a single project located under a workspace directory.

    Attributes:
        name: Project name (directory name under the workspace).
        root: Absolute path to the project directory.
        state_dir: Absolute path to the project's hidden state directory.
    """

    name: str
    root: Path
    state_dir: Path

    def exists(self) -> bool:
        return self.root.exists() and self.root.is_dir()

    def validate(self) -> None:
        if not self.exists():
            raise FileNotFoundError(f"Project directory not found: {self.root}")

    def ensure_state_dir(self) -> None:
        """Ensure the project's hidden state directory exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def ensure_gitignore_entry(self) -> None:
        """Ensure .agentsmithy is listed in .gitignore at project root.

        Creates .gitignore if it doesn't exist, or appends the entry if missing.
        """
        gitignore_path = self.root / ".gitignore"
        entry = ".agentsmithy"

        try:
            if gitignore_path.exists():
                # Read existing content
                content = gitignore_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # Check if entry already exists (exact match or with trailing slash)
                if any(line.strip() in (entry, f"{entry}/") for line in lines):
                    return  # Already present

                # Append entry (ensure newline before if file doesn't end with one)
                if content and not content.endswith("\n"):
                    gitignore_path.write_text(f"{content}\n{entry}\n", encoding="utf-8")
                else:
                    gitignore_path.write_text(f"{content}{entry}\n", encoding="utf-8")

                logger.info(
                    "Added .agentsmithy to existing .gitignore",
                    path=str(gitignore_path),
                    project=self.name,
                )
            else:
                # Create new .gitignore with the entry
                gitignore_path.write_text(f"{entry}\n", encoding="utf-8")
                logger.info(
                    "Created .gitignore with .agentsmithy entry",
                    path=str(gitignore_path),
                    project=self.name,
                )
        except Exception as e:
            # Log the error but don't fail - gitignore is nice to have but not critical
            logger.warning(
                "Failed to update .gitignore",
                error=str(e),
                path=str(gitignore_path),
                project=self.name,
            )

    # ---- Dialogs management (project-owned) ----
    @property
    def dialogs_dir(self) -> Path:
        """Directory for all dialog-related state for this project."""
        return self.state_dir / "dialogs"

    def ensure_dialogs_dir(self) -> None:
        """Ensure dialogs directory exists under the project state directory."""
        self.ensure_state_dir()
        self.dialogs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def dialogs_index_path(self) -> Path:
        return self.dialogs_dir / "index.json"

    def _now_iso(self) -> str:
        # Use Z suffix for UTC to simplify client parsing
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def load_dialogs_index(self) -> dict[str, Any]:
        """Load dialogs index; return default structure if missing or invalid."""
        self.ensure_dialogs_dir()
        if not self.dialogs_index_path.exists():
            return {"current_dialog_id": None, "dialogs": []}
        try:
            return json.loads(self.dialogs_index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"current_dialog_id": None, "dialogs": []}

    def save_dialogs_index(self, index: dict[str, Any]) -> None:
        """Atomically save dialogs index to disk."""
        self.ensure_dialogs_dir()
        tmp_path = self.dialogs_index_path.with_suffix(".tmp")
        data = json.dumps(index, ensure_ascii=False, indent=2)
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(self.dialogs_index_path)

    def get_dialog_dir(self, dialog_id: str) -> Path:
        """Return directory path for a given dialog id (without creating)."""
        return self.dialogs_dir / dialog_id

    def get_dialog_history(self, dialog_id: str) -> DialogHistory:
        """Get DialogHistory instance for a given dialog.

        Inspector dialog doesn't track metadata (no index.json entry).
        """
        track_metadata = dialog_id != "inspector"
        return DialogHistory(self, dialog_id, track_metadata=track_metadata)

    def create_dialog(self, title: str | None = None, set_current: bool = True) -> str:
        """Create a new dialog under this project and return its id.

        Creates the directory `.agentsmithy/dialogs/<dialog_id>/` and updates
        `.agentsmithy/dialogs/index.json` with metadata.
        """
        self.ensure_dialogs_dir()
        dialog_id = uuid.uuid4().hex  # simple unique id; can switch to ULID later
        dialog_dir = self.get_dialog_dir(dialog_id)
        dialog_dir.mkdir(parents=True, exist_ok=True)

        index = self.load_dialogs_index()
        now = self._now_iso()
        meta = {
            "id": dialog_id,
            "title": title or None,
            "created_at": now,
            "updated_at": now,
        }
        # Ensure dialogs is a list
        dialogs_list = list(index.get("dialogs", []))
        dialogs_list.append(meta)
        index["dialogs"] = dialogs_list
        if set_current:
            index["current_dialog_id"] = dialog_id
        self.save_dialogs_index(index)
        return dialog_id

    def list_dialogs(
        self,
        sort_by: str = "updated_at",
        descending: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return dialogs with optional sorting and filtering.

        sort_by: one of ["updated_at", "created_at"].
        """
        index = self.load_dialogs_index()
        items: list[dict[str, Any]] = list(index.get("dialogs", []))

        # Sort by timestamp field
        def sort_key(d: dict[str, Any]):
            ts = d.get(sort_by)
            # None timestamps should be treated as oldest
            return ts or ""

        items.sort(key=sort_key, reverse=descending)

        if offset:
            items = items[offset:]
        if limit is not None:
            items = items[:limit]
        return items

    def get_current_dialog_id(self) -> str | None:
        index = self.load_dialogs_index()
        cid = index.get("current_dialog_id")
        return cid if isinstance(cid, str) else None

    def set_current_dialog_id(self, dialog_id: str) -> None:
        index = self.load_dialogs_index()
        # Validate dialog exists
        dialog_ids = {d.get("id") for d in index.get("dialogs", [])}
        if dialog_id not in dialog_ids:
            raise ValueError(f"Dialog id not found: {dialog_id}")
        index["current_dialog_id"] = dialog_id
        self.save_dialogs_index(index)

    def upsert_dialog_meta(self, dialog_id: str, **fields: Any) -> None:
        """Update metadata for dialog in index; create entry if missing."""
        index = self.load_dialogs_index()
        dialogs_list: list[dict[str, Any]] = list(index.get("dialogs", []))
        found = False
        for d in dialogs_list:
            if d.get("id") == dialog_id:
                # Log what we're updating
                if fields:
                    logger.debug(
                        "Updating dialog metadata",
                        dialog_id=dialog_id,
                        fields=fields,
                        current_title=d.get("title"),
                    )
                d.update(fields)
                # Always bump updated_at when we touch metadata
                d["updated_at"] = self._now_iso()
                found = True
                break
        if not found:
            now = self._now_iso()
            meta = {
                "id": dialog_id,
                "title": fields.get("title"),
                "created_at": now,
                "updated_at": now,
            }
            dialogs_list.append(meta)
            logger.debug(
                "Created new dialog metadata",
                dialog_id=dialog_id,
                title=meta.get("title"),
            )
        index["dialogs"] = dialogs_list
        self.save_dialogs_index(index)

    def get_dialog_meta(self, dialog_id: str) -> dict[str, Any] | None:
        """Return metadata for a single dialog id, or None if absent."""
        index = self.load_dialogs_index()
        for d in index.get("dialogs", []):
            if d.get("id") == dialog_id:
                return d
        return None

    def delete_dialog(self, dialog_id: str) -> None:
        """Delete dialog directory and remove from index. If current, unset or pick latest.

        This operation removes `.agentsmithy/dialogs/<dialog_id>` recursively.
        """
        self.ensure_dialogs_dir()
        # Clear messages from SQLite for this dialog_id
        try:
            DialogHistory(self, dialog_id).clear()
        except Exception:
            pass
        # Remove directory if exists
        ddir = self.get_dialog_dir(dialog_id)
        if ddir.exists():
            shutil.rmtree(ddir, ignore_errors=True)

        # Update index
        index = self.load_dialogs_index()
        dialogs_list: list[dict[str, Any]] = [
            d for d in index.get("dialogs", []) if d.get("id") != dialog_id
        ]
        index["dialogs"] = dialogs_list

        if index.get("current_dialog_id") == dialog_id:
            # Choose a new current dialog: pick most recent by updated_at
            def _key(d: dict[str, Any]):
                return d.get("updated_at") or d.get("created_at") or ""

            new_current = None
            if dialogs_list:
                new_current = sorted(dialogs_list, key=_key, reverse=True)[0].get("id")
            index["current_dialog_id"] = new_current

        self.save_dialogs_index(index)

    # ---- RAG management (project-owned) ----
    @property
    def rag_dir(self) -> Path:
        """Directory for all RAG-related state for this project."""
        return self.state_dir / "rag"

    def ensure_rag_dirs(self) -> None:
        """Ensure RAG directories exist under the project state directory."""
        self.ensure_state_dir()
        (self.rag_dir / "chroma_db").mkdir(parents=True, exist_ok=True)

    def get_vector_store(self, collection_name: str = "agentsmithy_docs"):
        """Return a project-scoped VectorStoreManager instance.

        Lazy-import to avoid circular imports at module load time.
        """
        from agentsmithy.rag.vector_store import VectorStoreManager

        self.ensure_rag_dirs()
        return VectorStoreManager(self, collection_name=collection_name)

    async def rag_add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        collection_name: str = "agentsmithy_docs",
    ) -> list[str]:
        """Convenience method to add texts to this project's vector store."""
        vsm = self.get_vector_store(collection_name)
        return await vsm.add_texts(texts, metadatas=metadatas)

    async def rag_similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
        collection_name: str = "agentsmithy_docs",
    ):
        """Search this project's vector store for similar documents."""
        vsm = self.get_vector_store(collection_name)
        return await vsm.similarity_search(query, k=k, filter=filter)

    # ---- Metadata management ----
    @property
    def metadata_path(self) -> Path:
        return self.state_dir / "project.json"

    def has_metadata(self) -> bool:
        return self.metadata_path.exists()

    def load_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_metadata(self, metadata: dict[str, Any]) -> None:
        self.ensure_state_dir()
        tmp_path = self.metadata_path.with_suffix(".tmp")
        data = json.dumps(metadata, ensure_ascii=False, indent=2)
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(self.metadata_path)


class ProjectWorkspace:
    """Represents a workspace containing multiple projects.

    The workspace itself maintains a root-level hidden directory for global
    state. Individual projects can additionally keep their own hidden state
    directories inside each project folder.
    """

    def __init__(self, workdir: Path):
        self.workdir: Path = workdir.expanduser().resolve()
        if not self.workdir.exists() or not self.workdir.is_dir():
            raise NotADirectoryError(f"Invalid workdir: {self.workdir}")
        self.root_state_dir: Path = self.workdir / ".agentsmithy"

    def ensure_root_state(self) -> None:
        """Ensure the workspace-level hidden state directory exists."""
        self.root_state_dir.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        """Return a list of project directory names under the workspace."""
        return [p.name for p in self.workdir.iterdir() if p.is_dir()]

    def get_project(self, name: str) -> Project:
        """Get a Project by name (does not create files)."""
        project_root = (self.workdir / name).resolve()
        # Prevent escaping the workspace
        project_root.relative_to(self.workdir)
        project_state = project_root / ".agentsmithy"
        return Project(name=name, root=project_root, state_dir=project_state)


_workspace_singleton: ProjectWorkspace | None = None


def set_workspace(workdir: Path) -> ProjectWorkspace:
    """Create and set the global workspace singleton, ensuring root state."""
    global _workspace_singleton
    workspace = ProjectWorkspace(workdir)
    workspace.ensure_root_state()
    _workspace_singleton = workspace
    return workspace


def get_workspace() -> ProjectWorkspace:
    """Get the global workspace, initializing from env if needed.

    Requires set_workspace() to be called at startup.
    """
    global _workspace_singleton
    if _workspace_singleton is None:
        raise RuntimeError(
            "Workspace is not initialized. Call set_workspace() at startup."
        )
    return _workspace_singleton


def get_current_project() -> Project:
    """Return the active Project inferred from the current workspace.

    In setups where the working directory is the project directory, this
    provides a direct Project instance rooted at that path.
    """
    workspace = get_workspace()
    root = workspace.workdir
    return Project(name=root.name, root=root, state_dir=root / ".agentsmithy")
