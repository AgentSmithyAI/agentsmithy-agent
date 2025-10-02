from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

Vendor = Literal["openai", "anthropic", "xai", "deepseek", "other"]


class IProviderChatAdapter(ABC):
    """Interface for provider-specific chat model adapters.

    Adapters translate engine-agnostic inputs into concrete LangChain client
    class path and constructor kwargs.
    """

    model: str

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def vendor(self) -> Vendor:
        pass

    @abstractmethod
    def supports_temperature(self) -> bool:
        pass

    @abstractmethod
    def build_langchain(
        self,
        *,
        temperature: float | None,
        max_tokens: int | None,
        reasoning_effort: str,
    ) -> tuple[str, dict[str, Any]]:
        """Return (langchain_class_path, kwargs) for LC chat model instantiation."""
        raise NotImplementedError

    def stream_kwargs(self) -> dict[str, Any]:
        """Optional provider-specific kwargs to pass into astream()."""
        return {}
