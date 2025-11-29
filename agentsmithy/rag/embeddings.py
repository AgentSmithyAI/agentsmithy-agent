"""Embeddings module for RAG system."""

from langchain_core.embeddings import Embeddings

from agentsmithy.llm.providers.openai.provider_embeddings import (
    OpenAIEmbeddingsProvider,
)

# NOTE (PyInstaller): tiktoken registers OpenAI encodings (e.g., "cl100k_base") via
# the plugin module `tiktoken_ext.openai_public`. PyInstaller one-file builds do not
# auto-discover this plugin because it is imported dynamically by tiktoken at runtime.
# The explicit import below ensures the plugin is bundled and its encodings are
# registered, preventing "Unknown encoding cl100k_base" errors in the frozen binary.
# Do not remove unless the build system is updated to collect tiktoken_ext.
try:  # pragma: no cover
    import tiktoken_ext.openai_public  # noqa: F401
except Exception:
    # If the plugin isn't present, runtime will fail on usage; this keeps dev envs lenient.
    pass

from agentsmithy.llm.providers.types import Vendor


class EmbeddingsManager:
    """Manager for handling document embeddings."""

    def __init__(
        self, provider: Vendor | str = Vendor.OPENAI, model: str | None = None
    ):
        # Normalize provider to enum or string value
        self.provider: Vendor | str = provider
        self.model = model
        self._embeddings: Embeddings | None = None

    @property
    def embeddings(self) -> Embeddings:
        """Get embeddings instance."""
        if self._embeddings is None:
            provider_val = (
                self.provider.value
                if isinstance(self.provider, Vendor)
                else self.provider
            )
            if provider_val == Vendor.OPENAI.value:
                # OpenAIEmbeddingsProvider resolves config via workload -> provider chain
                self._embeddings = OpenAIEmbeddingsProvider(self.model).embeddings
            else:
                raise ValueError(f"Unknown embeddings provider: {provider_val}")

        return self._embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents asynchronously."""
        return await self.embeddings.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Embed query asynchronously."""
        return await self.embeddings.aembed_query(text)
