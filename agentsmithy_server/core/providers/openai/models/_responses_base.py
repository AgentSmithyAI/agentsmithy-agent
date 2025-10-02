from __future__ import annotations

from typing import Any, Literal

from ._base import OpenAIModelSpec


class _ResponsesFamilySpec(OpenAIModelSpec):
    family: Literal["responses"] = "responses"

    def supports_temperature(self) -> bool:
        return False

    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Build base kwargs for Responses API models (e.g., GPT-5 series)
        # Notes:
        # - temperature is not supported for reasoning models
        # - Responses API uses max_output_tokens instead of max_completion_tokens
        # - To receive reasoning summaries/events, include reasoning.summary
        base_kwargs: dict[str, Any] = {
            "model": self.name,
            "reasoning": {
                "effort": reasoning_effort,
                # Enable summaries of chain-of-thought (reasoning) where supported
                # Options: "auto", "detailed" (GPT-5), "concise" (not for GPT-5 per docs)
                "summary": "auto",
            },
        }
        if max_tokens is not None:
            base_kwargs["max_output_tokens"] = max_tokens
        return base_kwargs, {}
