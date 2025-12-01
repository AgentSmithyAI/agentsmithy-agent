from __future__ import annotations

from typing import Any, Literal

from agentsmithy.llm.providers.model_spec import IModelSpec
from agentsmithy.llm.providers.types import Vendor


class OpenAIModelSpec(IModelSpec):
    """OpenAI-specific model spec implementing the provider-agnostic interface."""

    # Set by decorator per concrete model; declared for type-checkers
    model_name: str | None = None
    family: Literal["responses", "chat_completions"]

    def __init__(self, name: str | None = None):
        # Allow subclasses to omit passing the name if decorator set class attribute
        if name is None:
            inferred = getattr(self, "model_name", None)
            if not inferred:
                raise ValueError(
                    "OpenAIModelSpec requires a model name; set via decorator or pass explicitly"
                )
            name = inferred
        super().__init__(name=name, vendor=Vendor.OPENAI)

    # Default behaviors can be overridden by concrete models
    def supports_temperature(
        self,
    ) -> bool:  # pragma: no cover - overridden in models where needed
        return True

    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[
        dict[str, Any], dict[str, Any]
    ]:  # pragma: no cover - must be implemented by subclasses
        raise NotImplementedError


class CustomChatCompletionsSpec(OpenAIModelSpec):
    """Fallback spec for custom/unknown models using standard chat completions API.

    Used for OpenAI-compatible endpoints (OpenRouter, LMStudio, etc.)
    or new OpenAI models not yet added to the registry.

    Note: For Ollama, use type: 'ollama' in provider config instead.
    """

    family: Literal["chat_completions"] = "chat_completions"

    def __init__(self, name: str):
        # Bypass decorator-based model_name, pass name directly
        super(OpenAIModelSpec, self).__init__(name=name, vendor=Vendor.OPENAI)

    def supports_temperature(self) -> bool:
        return True

    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        base_kwargs: dict[str, Any] = {
            "model": self.name,
        }
        if temperature is not None:
            base_kwargs["temperature"] = temperature
        if max_tokens is not None:
            base_kwargs["max_tokens"] = max_tokens
        model_kwargs: dict[str, Any] = {
            # Ensure usage is included in final chunk
            "stream_options": {"include_usage": True}
        }
        return base_kwargs, model_kwargs
