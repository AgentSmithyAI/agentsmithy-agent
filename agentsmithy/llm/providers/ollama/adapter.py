"""Ollama provider adapter.

Uses langchain_openai.ChatOpenAI with Ollama's OpenAI-compatible endpoint.
"""

from __future__ import annotations

from typing import Any

from agentsmithy.llm.providers.base_adapter import IProviderChatAdapter
from agentsmithy.llm.providers.model_spec import IModelSpec
from agentsmithy.llm.providers.types import Vendor

from .models import OllamaModelSpec


class OllamaChatAdapter(IProviderChatAdapter):
    """Adapter for Ollama models using OpenAI-compatible API."""

    def __init__(self, model: str, impl: IModelSpec):
        super().__init__(model)
        self._impl = impl

    def vendor(self) -> Vendor:
        return Vendor.OLLAMA

    def supports_temperature(self) -> bool:
        return self._impl.supports_temperature()

    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build LangChain ChatOpenAI kwargs for Ollama.

        Uses ChatOpenAI class but configured for Ollama endpoint.
        """
        base_kwargs, model_kwargs = self._impl.build_langchain_kwargs(
            temperature, max_tokens, reasoning_effort
        )
        if model_kwargs:
            base_kwargs["model_kwargs"] = model_kwargs
        # Use ChatOpenAI - Ollama is OpenAI-compatible
        return "langchain_openai.ChatOpenAI", base_kwargs

    def stream_kwargs(self) -> dict[str, Any]:
        """Return streaming kwargs - empty for Ollama.

        Ollama doesn't support stream_usage option.
        """
        return {}


def factory(model: str) -> IProviderChatAdapter | None:
    """Factory that creates adapter for any Ollama model.

    This factory is not used directly for model matching since Ollama
    models can have any name. Instead, it's used when provider type
    is explicitly set to 'ollama' in config.
    """
    # This factory doesn't auto-match models by name.
    # Ollama models are matched via provider type in config.
    return None


def create_ollama_adapter(model: str) -> OllamaChatAdapter:
    """Create an Ollama adapter for the given model name.

    Called by OpenAIProvider when provider type is 'ollama'.
    """
    impl = OllamaModelSpec(model)
    return OllamaChatAdapter(model, impl)
