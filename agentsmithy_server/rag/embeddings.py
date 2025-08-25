"""Embeddings module for RAG system."""

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings


class EmbeddingsManager:
    """Manager for handling document embeddings."""

    def __init__(self, provider: str = "openai", model: str | None = None):
        from agentsmithy_server.config import settings

        self.provider = provider
        self.model = model or settings.default_embedding_model
        self._embeddings: Embeddings | None = None

    @property
    def embeddings(self) -> Embeddings:
        """Get embeddings instance."""
        if self._embeddings is None:
            if self.provider == "openai":
                # Let SDK pick API key from environment; avoids SecretStr typing issues
                self._embeddings = OpenAIEmbeddings(model=self.model)
            else:
                raise ValueError(f"Unknown embeddings provider: {self.provider}")

        return self._embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents asynchronously."""
        return await self.embeddings.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Embed query asynchronously."""
        return await self.embeddings.aembed_query(text)
