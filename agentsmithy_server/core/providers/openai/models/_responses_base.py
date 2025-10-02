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
        base_kwargs: dict[str, Any] = {
            "model": self.name,
            # For responses family, temperature is not supported
            "reasoning": {"effort": reasoning_effort},
        }
        if max_tokens is not None:
            # Responses API expects max_completion_tokens
            base_kwargs["max_completion_tokens"] = max_tokens
        return base_kwargs, {}
