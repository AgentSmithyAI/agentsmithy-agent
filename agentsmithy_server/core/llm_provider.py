"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agentsmithy_server.config import settings
from agentsmithy_server.core.agent_config import (
    AgentConfig,
    get_agent_config_provider,
)
from agentsmithy_server.utils.logger import agent_logger


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def agenerate(
        self, messages: list[BaseMessage], stream: bool = False, **kwargs
    ) -> AsyncIterator[str] | str:
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
        # Resolve model/temperature from provider if not explicitly passed
        if model is None or temperature is None:
            cfg: AgentConfig = get_agent_config_provider().get_config(
                (agent_name or "").strip() or "universal_agent"
            )
            model = model or cfg.model
            temperature = temperature or cfg.temperature

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

        # Initialize LLM; use explicit API key if provided
        if self.api_key:
            # Note: langchain_openai expects SecretStr; use environment variable fallback instead
            import os

            os.environ.setdefault("OPENAI_API_KEY", str(self.api_key))
            self.llm = ChatOpenAI(
                model=self.model, temperature=self.temperature, streaming=True
            )
        else:
            self.llm = ChatOpenAI(
                model=self.model, temperature=self.temperature, streaming=True
            )

    async def agenerate(
        self, messages: list[BaseMessage], stream: bool = False, **kwargs
    ) -> AsyncIterator[str] | str:
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
    ) -> AsyncIterator[str]:
        """Generate streaming response."""
        async for chunk in self.llm.astream(messages, **kwargs):
            content = getattr(chunk, "content", None)
            if isinstance(content, str) and content:
                yield content

    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model

    def bind_tools(self, tools: list[BaseTool]) -> Any:
        """Bind tools to the LLM for function calling."""
        # Return a tool-bound runnable/LLM as provided by SDK
        return self.llm.bind_tools(tools)


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
