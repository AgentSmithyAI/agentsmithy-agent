"""Ollama model specifications.

Ollama uses OpenAI-compatible API but doesn't support some features:
- stream_options (include_usage)
- logprobs, n, best_of, echo, tool_choice, user
"""

from __future__ import annotations

from typing import Any, Literal

from agentsmithy.llm.providers.model_spec import IModelSpec
from agentsmithy.llm.providers.types import Vendor


class OllamaModelSpec(IModelSpec):
    """Model spec for Ollama local models.

    Uses ChatOpenAI under the hood but without stream_options
    which Ollama doesn't support.
    """

    family: Literal["chat_completions"] = "chat_completions"

    def __init__(self, name: str):
        super().__init__(name=name, vendor=Vendor.OLLAMA)

    def supports_temperature(self) -> bool:
        return True

    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build kwargs for ChatOpenAI without stream_options.

        Ollama doesn't support stream_options.include_usage, so we omit it.
        """
        base_kwargs: dict[str, Any] = {
            "model": self.name,
        }
        if temperature is not None:
            base_kwargs["temperature"] = temperature
        if max_tokens is not None:
            base_kwargs["max_tokens"] = max_tokens

        # No model_kwargs - Ollama doesn't support stream_options
        model_kwargs: dict[str, Any] = {}
        return base_kwargs, model_kwargs
