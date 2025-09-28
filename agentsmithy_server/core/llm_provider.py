"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agentsmithy_server.config import settings
from agentsmithy_server.core.providers.openai_init import build_openai_langchain_kwargs
from agentsmithy_server.utils.logger import agent_logger


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
    """OpenAI LLM provider implementation."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
        agent_name: str | None = None,
    ):
        # Use explicit model/temperature or fall back to global settings only
        self.model = model or settings.default_model
        self.temperature = temperature or settings.default_temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.api_key = api_key or settings.openai_api_key

        # Validate that model is set
        if not self.model:
            raise ValueError(
                "LLM model not specified. Please set DEFAULT_MODEL in .env file "
                "or pass model parameter explicitly"
            )

        agent_logger.info(
            "Initializing OpenAI provider",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Base kwargs split to allow per-family specialization
        base_kwargs, model_kwargs = build_openai_langchain_kwargs(
            self.model, self.temperature, self.max_tokens
        )
        if model_kwargs:
            base_kwargs["model_kwargs"] = model_kwargs

        # Initialize LLM; use explicit API key if provided
        if self.api_key:
            # Note: langchain_openai expects SecretStr; use environment variable fallback instead
            import os

            os.environ.setdefault("OPENAI_API_KEY", str(self.api_key))
            try:
                agent_logger.debug(
                    "Initializing ChatOpenAI", base_kwargs_keys=list(base_kwargs.keys())
                )
            except Exception:
                pass
            self.llm = ChatOpenAI(**base_kwargs)
        else:
            try:
                agent_logger.debug(
                    "Initializing ChatOpenAI", base_kwargs_keys=list(base_kwargs.keys())
                )
            except Exception:
                pass
            self.llm = ChatOpenAI(**base_kwargs)

        # Track last observed usage in streaming mode
        self._last_usage: dict[str, Any] | None = None

    async def agenerate(
        self, messages: list[BaseMessage], stream: bool = False, **kwargs
    ) -> AsyncIterator[str | dict[str, Any]] | str:
        """Generate response from messages."""
        if stream:
            return self._agenerate_stream(messages, **kwargs)
        else:
            response = await self.llm.ainvoke(messages, **kwargs)
            content = getattr(response, "content", "")
            if isinstance(content, str):
                return content
            # Fallback to stringified
            return str(content)

    async def _agenerate_stream(
        self, messages: list[BaseMessage], **kwargs
    ) -> AsyncIterator[str | dict[str, Any]]:
        """Generate streaming response."""
        async for chunk in self.llm.astream(messages, **kwargs):
            content = getattr(chunk, "content", None)
            if isinstance(content, str) and content:
                yield {"type": "chat", "content": content}

    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model

    def bind_tools(self, tools: list[BaseTool]) -> Any:
        """Bind tools to the LLM for function calling."""
        # Return a tool-bound runnable/LLM as provided by SDK
        return self.llm.bind_tools(tools)

    def get_last_usage(self) -> dict[str, Any] | None:
        """Return last observed usage from streaming; may be None if unavailable."""
        return None


class LLMFactory:
    """Factory for creating LLM providers."""

    _providers: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
    }

    @classmethod
    def create(cls, provider: str = "openai", **kwargs) -> LLMProvider:
        """Create an LLM provider instance."""
        if provider not in cls._providers:
            raise ValueError(f"Unknown provider: {provider}")

        provider_class = cls._providers[provider]
        provider_instance: LLMProvider = provider_class(**kwargs)
        return provider_instance

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class
