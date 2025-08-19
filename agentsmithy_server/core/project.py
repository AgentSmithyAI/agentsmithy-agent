"""Project and workspace management.

This module defines an extensible Project entity and a ProjectWorkspace that
own directory-related concerns. It is designed to be expanded with metadata,
configuration, indexing, and other project-level behaviors.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        from agentsmithy_server.rag.vector_store import VectorStoreManager

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

    Requires AGENTSMITHY_WORKDIR to be set if not explicitly initialized via
    set_workspace().
    """
    global _workspace_singleton
    if _workspace_singleton is not None:
        return _workspace_singleton

    workdir_env = os.getenv("AGENTSMITHY_WORKDIR")
    if not workdir_env:
        raise RuntimeError(
            "AGENTSMITHY_WORKDIR is not set. Initialize workspace at startup."
        )
    workspace = ProjectWorkspace(Path(workdir_env))
    workspace.ensure_root_state()
    _workspace_singleton = workspace
    return workspace
