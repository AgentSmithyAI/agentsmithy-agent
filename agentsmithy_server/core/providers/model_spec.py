from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import Vendor


class IModelSpec(ABC):
    """Provider-agnostic interface for per-model configuration and capabilities.

    Implementations may adapt provider-specific options but must expose a unified
    way to configure downstream clients (e.g., LangChain wrappers).
    """

    name: str
    vendor: Vendor  # e.g., Vendor.OPENAI, Vendor.ANTHROPIC

    def __init__(self, name: str, vendor: Vendor) -> None:
        self.name = name
        self.vendor = vendor

    @abstractmethod
    def supports_temperature(self) -> bool:
        pass

    @abstractmethod
    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (base_kwargs, model_kwargs) for a LangChain chat model implementation.
        base_kwargs go to the concrete LC class; model_kwargs are passed via model_kwargs.
        """
        pass
