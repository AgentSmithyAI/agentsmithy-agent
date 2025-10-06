"""OpenAI embeddings provider.

Provides a thin wrapper around `langchain_openai.OpenAIEmbeddings` that reads
nested OpenAI embeddings configuration from settings and prepares kwargs.
"""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from agentsmithy_server.config import settings


class OpenAIEmbeddingsProvider:
    def __init__(self, model: str | None = None):
        self.model = model or settings.openai_embeddings_model
        if not self.model:
            raise ValueError("OpenAI embeddings model must be specified")

    @property
    def embeddings(self) -> Embeddings:
        kwargs: dict[str, Any] = {"model": self.model}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        # Provider-wide options from providers.openai.options
        prov = settings.get_provider_config("openai")
        extra = prov.get("options") if isinstance(prov, dict) else None
        if isinstance(extra, dict) and extra:
            kwargs.update(extra)
        return OpenAIEmbeddings(**kwargs)
