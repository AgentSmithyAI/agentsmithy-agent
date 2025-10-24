"""Vector store module for RAG system.

Persistency is project-scoped: vectors are stored inside the selected
project's hidden state directory.
"""

import os
from pathlib import Path
from typing import Any

# NOTE (PyInstaller): Import Chroma Settings to explicitly disable telemetry.
# Chroma's telemetry can trigger a dynamic import of `chromadb.telemetry.product.posthog`,
# which PyInstaller one-file builds do not auto-discover. Disabling telemetry avoids
# runtime import errors in the frozen binary. Do not remove unless you also adjust
# PyInstaller hidden imports to include Chroma telemetry modules.
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agentsmithy.core.project import Project
from agentsmithy.rag.embeddings import EmbeddingsManager


class VectorStoreManager:
    """Manager for vector store operations, scoped to a Project."""

    def __init__(
        self,
        project: Project,
        collection_name: str = "agentsmithy_docs",
    ):
        self.project = project
        # Store under project state directory
        self.persist_directory = str(
            Path(self.project.state_dir).joinpath("rag", "chroma_db")
        )
        self.collection_name = collection_name
        self.embeddings_manager = EmbeddingsManager()
        self._vectorstore: Chroma | None = None

        # Ensure project state and persist directory exist
        self.project.ensure_state_dir()
        os.makedirs(self.persist_directory, exist_ok=True)

    @property
    def vectorstore(self) -> Chroma:
        """Get or create vector store instance."""
        if self._vectorstore is None:
            self._vectorstore = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings_manager.embeddings,
                persist_directory=self.persist_directory,
                # NOTE (PyInstaller): Keep anonymized_telemetry disabled to prevent Chroma from
                # importing PostHog at runtime inside the frozen binary. If you must enable
                # telemetry, ensure PyInstaller collects `chromadb.telemetry.product.posthog`
                # and its dependencies.
                client_settings=Settings(anonymized_telemetry=False),
            )
        return self._vectorstore

    async def add_documents(
        self,
        documents: list[Document],
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[str]:
        """Add documents to vector store."""
        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )

        chunks = text_splitter.split_documents(documents)

        # Add chunks to vector store
        ids = self.vectorstore.add_documents(chunks)

        return ids

    async def add_texts(
        self, texts: list[str], metadatas: list[dict[str, Any]] | None = None
    ) -> list[str]:
        """Add texts directly to vector store."""
        ids = self.vectorstore.add_texts(texts, metadatas=metadatas)
        return ids

    async def similarity_search(
        self, query: str, k: int = 4, filter: dict[str, Any] | None = None
    ) -> list[Document]:
        """Search for similar documents."""
        return self.vectorstore.similarity_search(query, k=k, filter=filter)

    async def asimilarity_search_with_score(
        self, query: str, k: int = 4, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        """Search for similar documents with relevance scores."""
        return self.vectorstore.similarity_search_with_score(query, k=k, filter=filter)

    def delete_collection(self):
        """Delete the entire collection."""
        if self._vectorstore:
            self._vectorstore.delete_collection()
            self._vectorstore = None

    def persist(self):
        """Persist the vector store to disk."""
        if self._vectorstore and self.persist_directory:
            self._vectorstore.persist()

    async def index_file(
        self, file_path: str, content: str | None = None, chunk_size: int = 1000
    ) -> list[str]:
        """Index a single file in the vector store.

        Args:
            file_path: Relative or absolute path to the file
            content: File content (if None, will read from disk)
            chunk_size: Size of chunks for splitting

        Returns:
            List of chunk IDs added to the store
        """
        import hashlib
        from datetime import UTC, datetime

        # Delete existing chunks for this file
        self.delete_by_source(file_path)

        # Read content if not provided
        if content is None:
            try:
                abs_path = (
                    Path(file_path)
                    if Path(file_path).is_absolute()
                    else self.project.root / file_path
                )
                content = abs_path.read_text(encoding="utf-8")
            except Exception:
                # File doesn't exist or can't be read
                return []

        # Calculate content hash for consistency checking
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Create document with metadata including hash
        doc = Document(
            page_content=content,
            metadata={
                "source": str(file_path),
                "hash": content_hash,
                "indexed_at": datetime.now(UTC).isoformat(),
            },
        )

        # Split and add
        ids = await self.add_documents([doc], chunk_size=chunk_size)
        return ids

    async def has_file(self, file_path: str) -> bool:
        """Check if a file is indexed in the vector store.

        Args:
            file_path: Path to check

        Returns:
            True if file has indexed chunks
        """
        try:
            # Try to find any documents with this source
            results = self.vectorstore.get(where={"source": str(file_path)})
            return len(results.get("ids", [])) > 0
        except Exception:
            return False

    def delete_by_source(self, file_path: str) -> None:
        """Delete all chunks for a specific file.

        Args:
            file_path: Path of the file to remove from index
        """
        try:
            # Chroma supports delete with filter
            self.vectorstore.delete(where={"source": str(file_path)})
        except Exception:
            # If delete fails (e.g., file not indexed), ignore
            pass

    async def reindex_file(self, file_path: str) -> list[str]:
        """Reindex a file after it has been modified.

        Args:
            file_path: Path to the file

        Returns:
            List of chunk IDs, or empty list if file doesn't exist
        """
        abs_path = (
            Path(file_path)
            if Path(file_path).is_absolute()
            else self.project.root / file_path
        )

        if abs_path.exists():
            # File exists - reindex it
            return await self.index_file(str(file_path))
        else:
            # File was deleted - remove from index
            self.delete_by_source(str(file_path))
            return []

    def get_indexed_files(self) -> dict[str, str]:
        """Get all indexed files with their hashes.

        Returns:
            Dictionary mapping file paths to their stored hashes
        """
        try:
            # Get all documents from vector store
            results = self.vectorstore.get()

            # Extract unique files with their hashes
            files_dict = {}
            if results and "metadatas" in results:
                for metadata in results["metadatas"]:
                    if metadata and "source" in metadata:
                        source = metadata["source"]
                        file_hash = metadata.get("hash", "")
                        # Only store if we haven't seen this file yet
                        # (multiple chunks from same file will have same hash)
                        if source not in files_dict:
                            files_dict[source] = file_hash

            return files_dict
        except Exception:
            return {}

    async def sync_files_if_needed(self) -> dict[str, int]:
        """Check all indexed files and reindex if hash mismatch.

        Returns:
            Dictionary with sync results:
            - "checked": number of files checked
            - "reindexed": number of files reindexed
            - "removed": number of files removed (deleted from disk)
        """
        import hashlib

        indexed_files = self.get_indexed_files()
        stats = {"checked": 0, "reindexed": 0, "removed": 0}

        for file_path, stored_hash in indexed_files.items():
            stats["checked"] += 1

            # Resolve file path
            abs_path = (
                Path(file_path)
                if Path(file_path).is_absolute()
                else self.project.root / file_path
            )

            # Check if file exists
            if not abs_path.exists():
                # File was deleted - remove from index
                self.delete_by_source(file_path)
                stats["removed"] += 1
                continue

            # Read current content and calculate hash
            try:
                current_content = abs_path.read_text(encoding="utf-8")
                current_hash = hashlib.md5(current_content.encode("utf-8")).hexdigest()

                # Compare hashes
                if current_hash != stored_hash:
                    # Hash mismatch - reindex
                    await self.index_file(file_path, current_content)
                    stats["reindexed"] += 1
            except Exception:
                # Can't read file - skip
                continue

        return stats
