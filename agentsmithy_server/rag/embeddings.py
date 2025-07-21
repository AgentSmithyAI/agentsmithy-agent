"""Embeddings module for RAG system."""

from typing import List, Optional

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from agentsmithy_server.config import settings


class EmbeddingsManager:
    """Manager for handling document embeddings."""

    def __init__(self, provider: str = "openai", model: Optional[str] = None):
        self.provider = provider
        self.model = model or "text-embedding-3-small"
        self._embeddings: Optional[Embeddings] = None

    @property
    def embeddings(self) -> Embeddings:
        """Get embeddings instance."""
        if self._embeddings is None:
            if self.provider == "openai":
                self._embeddings = OpenAIEmbeddings(
                    model=self.model, api_key=settings.openai_api_key
                )
            else:
                raise ValueError(f"Unknown embeddings provider: {self.provider}")

        return self._embeddings

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed documents asynchronously."""
        return await self.embeddings.aembed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        """Embed query asynchronously."""
        return await self.embeddings.aembed_query(text)
