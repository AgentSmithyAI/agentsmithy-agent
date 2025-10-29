"""Vector store module for RAG system.

Persistency is project-scoped: vectors are stored inside the selected
project's hidden state directory.
"""

import asyncio
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

        # If no chunks (e.g., empty documents), return empty list
        if not chunks:
            return []

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
        file_size = 0
        file_mtime = 0
        if content is None:
            try:
                abs_path = (
                    Path(file_path)
                    if Path(file_path).is_absolute()
                    else self.project.root / file_path
                )
                content = abs_path.read_text(encoding="utf-8")
                # Get file stats for optimization
                stat = abs_path.stat()
                file_size = stat.st_size
                file_mtime = int(stat.st_mtime)
            except Exception:
                # File doesn't exist or can't be read
                return []
        else:
            # Content provided, estimate size
            file_size = len(content.encode("utf-8"))

        # Calculate content hash for consistency checking
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Create document with metadata including hash, size, and mtime
        doc = Document(
            page_content=content,
            metadata={
                "source": str(file_path),
                "hash": content_hash,
                "size": file_size,
                "mtime": file_mtime,
                "indexed_at": datetime.now(UTC).isoformat(),
            },
        )

        # Split and add
        ids = await self.add_documents([doc], chunk_size=chunk_size)

        from agentsmithy.utils.logger import rag_logger

        rag_logger.debug(
            "Indexed file in RAG",
            file=file_path,
            chunks=len(ids),
            hash=content_hash[:8],
        )

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

    async def reindex_files(self, file_paths: list[str]) -> int:
        """Reindex multiple files if they were previously indexed.

        Uses concurrent processing with asyncio.gather for better performance.

        Args:
            file_paths: List of file paths to check and reindex

        Returns:
            Number of files that were reindexed
        """

        # Filter files that are actually indexed
        files_to_reindex = []
        for file_path in file_paths:
            if await self.has_file(file_path):
                files_to_reindex.append(file_path)

        # Reindex all files concurrently
        if files_to_reindex:
            await asyncio.gather(
                *[self.reindex_file(file_path) for file_path in files_to_reindex]
            )

        return len(files_to_reindex)

    def get_file_metadata(self, file_path: str) -> dict[str, Any] | None:
        """Get metadata for a specific indexed file.

        Args:
            file_path: Path to file

        Returns:
            Metadata dict or None if file not indexed
        """
        try:
            results = self.vectorstore.get(where={"source": str(file_path)})
            if results and "metadatas" in results and results["metadatas"]:
                # Return first matching metadata
                return results["metadatas"][0]
        except Exception:
            # Non-critical: failure to retrieve metadata just means the file is
            # not indexed or the store is unavailable; treat as missing.
            return None
        return None

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

    async def _check_and_reindex_file(
        self,
        file_path: str,
        stored_hash: str,
        abs_path: Path,
        semaphore: asyncio.Semaphore,
    ) -> tuple[str, bool]:
        """Check and reindex a single file if needed.

        Args:
            file_path: Relative file path
            stored_hash: Previously stored hash
            abs_path: Absolute path to file
            semaphore: Semaphore for concurrency control

        Returns:
            Tuple of (status, content) where status is "reindexed", "skipped", or "error"
        """
        import hashlib

        async with semaphore:
            try:
                # Read file in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                current_content = await loop.run_in_executor(
                    None, abs_path.read_text, "utf-8"
                )

                # Compute hash in thread pool (can be CPU intensive for large files)
                current_hash = await loop.run_in_executor(
                    None,
                    lambda: hashlib.md5(current_content.encode("utf-8")).hexdigest(),
                )

                # Compare hashes
                if current_hash != stored_hash:
                    # Hash mismatch - reindex
                    await self.index_file(file_path, current_content)
                    return ("reindexed", True)
                else:
                    return ("skipped", False)
            except Exception:
                # Can't read file - skip
                return ("error", False)

    async def sync_files_if_needed(self) -> dict[str, int]:
        """Check all indexed files and reindex if hash mismatch.

        Optimization: Only reads files that likely changed (based on mtime/size check).
        Uses parallel processing with concurrency limits for efficient batch processing.

        Returns:
            Dictionary with sync results:
            - "checked": number of files checked
            - "reindexed": number of files reindexed
            - "removed": number of files removed (deleted from disk)
            - "skipped": number of files skipped (unchanged)
        """
        from agentsmithy.utils.logger import rag_logger

        indexed_files = self.get_indexed_files()
        stats = {"checked": 0, "reindexed": 0, "removed": 0, "skipped": 0}

        if indexed_files:
            rag_logger.debug("RAG sync started", files_to_check=len(indexed_files))

        # First pass: check existence and quick mtime/size check
        files_to_read: list[tuple[str, str, Path]] = []

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

            # Quick optimization: check mtime and size from metadata
            try:
                # Get stored metadata for this file
                metadata = self.get_file_metadata(file_path)
                stored_mtime = metadata.get("mtime", 0) if metadata else 0
                stored_size = metadata.get("size", 0) if metadata else 0

                # Get current file stats (fast - no file read!)
                stat = abs_path.stat()
                current_mtime = int(stat.st_mtime)
                current_size = stat.st_size

                # If mtime and size unchanged, skip reading file
                if current_mtime == stored_mtime and current_size == stored_size:
                    stats["skipped"] += 1
                    continue
            except Exception:
                # Metadata not available or stat failed, need to read
                pass

            # File potentially changed, need to read and verify
            files_to_read.append((file_path, stored_hash, abs_path))

        # Second pass: read and hash files in parallel with concurrency limit
        if files_to_read:
            # Limit concurrent file operations to avoid overwhelming the system
            # 10 concurrent operations is a good balance for most systems
            semaphore = asyncio.Semaphore(10)

            # Create tasks for all files
            tasks = [
                self._check_and_reindex_file(
                    file_path, stored_hash, abs_path, semaphore
                )
                for file_path, stored_hash, abs_path in files_to_read
            ]

            # Process all tasks in parallel (with semaphore limiting concurrency)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for result in results:
                if isinstance(result, BaseException):
                    # Skip exceptions (errors during file processing)
                    continue
                # Now result is guaranteed to be tuple[str, bool]
                status, _ = result
                if status == "reindexed":
                    stats["reindexed"] += 1
                elif status == "skipped":
                    stats["skipped"] += 1
                # Errors are silently ignored (already counted as not reindexed)

        if stats["reindexed"] > 0 or stats["removed"] > 0:
            rag_logger.debug(
                "RAG sync completed",
                checked=stats["checked"],
                reindexed=stats["reindexed"],
                removed=stats["removed"],
                skipped=stats["skipped"],
            )

        return stats
