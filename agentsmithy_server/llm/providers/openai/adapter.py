from __future__ import annotations

from typing import Any

from agentsmithy_server.llm.providers.base_adapter import IProviderChatAdapter
from agentsmithy_server.llm.providers.model_spec import IModelSpec
from agentsmithy_server.llm.providers.openai.models import (
    get_model_spec as get_openai_model_spec,
)
from agentsmithy_server.llm.providers.types import Vendor


class OpenAIChatAdapter(IProviderChatAdapter):
    def __init__(self, model: str, impl: IModelSpec):
        super().__init__(model)
        self._impl = impl

    def vendor(self) -> Vendor:
        return Vendor.OPENAI

    def supports_temperature(self) -> bool:
        return self._impl.supports_temperature()

    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        base_kwargs, model_kwargs = self._impl.build_langchain_kwargs(
            temperature, max_tokens, reasoning_effort
        )
        if model_kwargs:
            base_kwargs["model_kwargs"] = model_kwargs
        return "langchain_openai.ChatOpenAI", base_kwargs

    def stream_kwargs(self) -> dict[str, Any]:
        # Responses family does not support stream_usage, chat_completions does
        family = getattr(self._impl, "family", "chat_completions")
        if family == "responses":
            return {}
        return {"stream_usage": True}


def factory(model: str) -> IProviderChatAdapter | None:
    try:
        impl = get_openai_model_spec(model)
    except Exception:
        return None
    return OpenAIChatAdapter(model, impl)
