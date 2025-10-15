from __future__ import annotations

from typing import Any

from agentsmithy_server.core.providers.base_adapter import IProviderChatAdapter
from agentsmithy_server.core.providers.types import Vendor


class LlamaChatAdapter(IProviderChatAdapter):
    """Adapter for local Llama models via llama.cpp."""

    def __init__(self, model: str):
        super().__init__(model)

    def vendor(self) -> Vendor:
        return Vendor.LLAMA

    def supports_temperature(self) -> bool:
        return True

    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build LangChain ChatLlamaCpp initialization kwargs.

        The model path is expected to be provided in the configuration.
        """
        kwargs = {
            "model_path": self.model,  # model here is the path to .gguf file
        }

        if temperature is not None:
            kwargs["temperature"] = temperature

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # Default settings that can be overridden by provider config
        kwargs.setdefault("n_ctx", 8192)
        kwargs.setdefault("n_threads", 8)
        kwargs.setdefault("verbose", False)

        return "langchain_community.chat_models.ChatLlamaCpp", kwargs

    def stream_kwargs(self) -> dict[str, Any]:
        """Llama.cpp streaming doesn't need special kwargs."""
        return {}


def factory(model: str) -> IProviderChatAdapter | None:
    """Factory function for Llama adapter.

    This factory is invoked for any model path that looks like a .gguf file
    or when explicitly configured as llama provider.
    """
    # Accept any model that ends with .gguf or starts with "llama:"
    if model.endswith(".gguf") or model.startswith("llama:"):
        # Strip prefix if present
        actual_path = model.replace("llama:", "", 1) if model.startswith("llama:") else model
        return LlamaChatAdapter(actual_path)
    return None

