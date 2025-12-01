"""Anthropic provider adapter.

Uses langchain_anthropic.ChatAnthropic for Claude models.
"""

from __future__ import annotations

from typing import Any

from agentsmithy.llm.providers.base_adapter import IProviderChatAdapter
from agentsmithy.llm.providers.model_spec import IModelSpec
from agentsmithy.llm.providers.types import Vendor

from .models import SUPPORTED_ANTHROPIC_CHAT_MODELS, AnthropicModelSpec


class AnthropicChatAdapter(IProviderChatAdapter):
    """Adapter for Anthropic Claude models."""

    def __init__(self, model: str, impl: IModelSpec):
        super().__init__(model)
        self._impl = impl

    def vendor(self) -> Vendor:
        return Vendor.ANTHROPIC

    def supports_temperature(self) -> bool:
        return self._impl.supports_temperature()

    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        """Build LangChain ChatAnthropic kwargs.

        Uses ChatAnthropic class from langchain_anthropic.
        """
        base_kwargs, model_kwargs = self._impl.build_langchain_kwargs(
            temperature, max_tokens, reasoning_effort
        )
        if model_kwargs:
            base_kwargs["model_kwargs"] = model_kwargs
        return "langchain_anthropic.ChatAnthropic", base_kwargs

    def stream_kwargs(self) -> dict[str, Any]:
        """Return streaming kwargs for Anthropic.

        Anthropic's streaming includes usage by default in the final message.
        """
        return {}


def create_anthropic_adapter(model: str) -> AnthropicChatAdapter:
    """Create an Anthropic adapter for the given model name.

    Called by OpenAIProvider when provider type is 'anthropic'.
    """
    impl = AnthropicModelSpec(model)
    return AnthropicChatAdapter(model, impl)


def factory(model: str) -> IProviderChatAdapter | None:
    """Factory function for registry-based adapter resolution.

    Returns an adapter if the model is a known Anthropic model,
    None otherwise (allows other adapters to try).
    """
    # Check if it's a known Anthropic model
    if model in SUPPORTED_ANTHROPIC_CHAT_MODELS:
        impl = AnthropicModelSpec(model)
        return AnthropicChatAdapter(model, impl)

    # Check if model name suggests Anthropic (e.g., starts with 'claude')
    if model.startswith("claude"):
        impl = AnthropicModelSpec(model)
        return AnthropicChatAdapter(model, impl)

    return None
