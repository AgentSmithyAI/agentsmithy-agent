"""Embeddings module for RAG system."""

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

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

from agentsmithy_server.core.providers.types import Vendor


class EmbeddingsManager:
    """Manager for handling document embeddings."""

    def __init__(
        self, provider: Vendor | str = Vendor.OPENAI, model: str | None = None
    ):
        from agentsmithy_server.config import settings

        # Normalize provider to enum or string value
        self.provider: Vendor | str = provider
        self.model = model or settings.embedding_model
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
                # Let SDK pick API key from environment; avoids SecretStr typing issues
                from agentsmithy_server.config import settings

                kwargs = {"model": self.model}
                if settings.openai_base_url:
                    kwargs["base_url"] = settings.openai_base_url
                self._embeddings = OpenAIEmbeddings(**kwargs)
            else:
                raise ValueError(f"Unknown embeddings provider: {provider_val}")

        return self._embeddings

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents asynchronously."""
        return await self.embeddings.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Embed query asynchronously."""
        return await self.embeddings.aembed_query(text)
