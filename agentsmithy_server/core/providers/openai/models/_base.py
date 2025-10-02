from __future__ import annotations

from typing import Any, Literal

from agentsmithy_server.core.providers.model_spec import IModelSpec


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
        super().__init__(name=name, vendor="openai")

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
