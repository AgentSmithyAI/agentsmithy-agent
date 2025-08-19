"""Vector store module for RAG system.

Persistency is project-scoped: vectors are stored inside the selected
project's hidden state directory.
"""

import os
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agentsmithy_server.core.project import Project
from agentsmithy_server.rag.embeddings import EmbeddingsManager


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
        self._vectorstore = None

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
