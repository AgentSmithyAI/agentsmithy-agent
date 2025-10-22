from __future__ import annotations

from typing import Any, Literal

from . import register_model
from ._base import OpenAIModelSpec


@register_model("gpt-oss:20b")
class GPTOss20BConfig(OpenAIModelSpec):
    family: Literal["chat_completions"] = "chat_completions"

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

