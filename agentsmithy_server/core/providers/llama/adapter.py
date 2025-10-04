from __future__ import annotations

from typing import Any

from agentsmithy_server.core.providers.base_adapter import IProviderChatAdapter
from agentsmithy_server.core.providers.types import Vendor


class LlamaChatAdapter(IProviderChatAdapter):
    """Adapter for llama.cpp server."""

    def __init__(self, model: str):
        super().__init__(model)

    def vendor(self) -> Vendor:
        return Vendor.OTHER  # llama provider

    def supports_temperature(self) -> bool:
        return True

    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build LangChain kwargs for local llama.cpp server."""
        base_kwargs: dict[str, Any] = {"model": self.model}

        if temperature is not None:
            base_kwargs["temperature"] = temperature

        if max_tokens is not None:
            base_kwargs["max_tokens"] = max_tokens

        # Use custom Granite wrapper for granite models
        if "granite" in self.model.lower():
            return (
                "agentsmithy_server.core.providers.llama.chat_granite.GraniteChatOpenAI",
                base_kwargs,
            )

        return "langchain_openai.ChatOpenAI", base_kwargs

    def stream_kwargs(self) -> dict[str, Any]:
        return {}


def factory(model: str) -> IProviderChatAdapter | None:
    """Factory function to create LlamaChatAdapter for granite models."""
    # Accept any model with "granite" in the name as llama provider
    if "granite" in model.lower():
        return LlamaChatAdapter(model)
    return None
