"""OpenAI embeddings provider.

Resolves embeddings configuration via workload -> provider chain.
"""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from agentsmithy.config import settings


class OpenAIEmbeddingsProvider:
    def __init__(self, model: str | None = None):
        # Resolve via models.embeddings.workload -> workloads.<name> -> providers.<name>
        embeddings_cfg = settings._get("models.embeddings", None)
        if not isinstance(embeddings_cfg, dict):
            raise ValueError(
                "Embeddings configuration not found. "
                "Check models.embeddings in your config."
            )

        workload_name = embeddings_cfg.get("workload")
        if not workload_name:
            raise ValueError(
                "Embeddings has no workload specified. "
                "Set models.embeddings.workload in your config."
            )

        workload_config = settings._get(f"workloads.{workload_name}", None)
        if not isinstance(workload_config, dict):
            raise ValueError(
                f"Workload '{workload_name}' not found in configuration. "
                f"Check workloads.{workload_name} in your config."
            )

        provider_name = workload_config.get("provider")
        if not provider_name:
            raise ValueError(
                f"Workload '{workload_name}' has no provider specified. "
                f"Set workloads.{workload_name}.provider in your config."
            )

        provider_def = settings._get(f"providers.{provider_name}", None)
        if not isinstance(provider_def, dict):
            raise ValueError(
                f"Provider '{provider_name}' not found in configuration. "
                f"Check providers.{provider_name} in your config."
            )

        # Resolve from config
        resolved_model = workload_config.get("model") or provider_def.get("model")
        resolved_api_key = provider_def.get("api_key")
        resolved_base_url = provider_def.get("base_url")
        resolved_options = provider_def.get("options", {})

        # Constructor arg overrides config
        self.model = model or resolved_model
        self.api_key = resolved_api_key
        self.base_url = resolved_base_url
        self.options = resolved_options if isinstance(resolved_options, dict) else {}

        if not self.model:
            raise ValueError(
                "Embeddings model not specified. Configure workloads.<name>.model "
                "or providers.<name>.model in your config."
            )

    @property
    def embeddings(self) -> Embeddings:
        kwargs: dict[str, Any] = {"model": self.model}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.options:
            kwargs.update(self.options)
        return OpenAIEmbeddings(**kwargs)
