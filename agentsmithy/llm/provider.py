"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def agenerate(
        self, messages: list[BaseMessage], stream: bool = False, **kwargs
    ) -> AsyncIterator[str | dict[str, Any]] | str:
        """Generate response from messages."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name."""
        pass

    @abstractmethod
    def bind_tools(self, tools: list[BaseTool]) -> Any:
        """Bind tools to the LLM for function calling."""
        pass


class OpenAIProvider(LLMProvider):
    """Deprecated shim: import moved to providers.openai.provider.OpenAIProvider.

    Kept for backward compatibility with existing imports in the codebase.
    """

    def __init__(self, *args, **kwargs):  # pragma: no cover - thin wrapper
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider as _P

        self.__class__ = _P
        _P.__init__(self, *args, **kwargs)
