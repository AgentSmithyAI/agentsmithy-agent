"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional, Union, Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agentsmithy_server.config import settings
from agentsmithy_server.utils.logger import agent_logger


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def agenerate(
        self, messages: List[BaseMessage], stream: bool = False, **kwargs
    ) -> Union[AsyncIterator[str], str]:
        """Generate response from messages."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name."""
        pass
    
    @abstractmethod
    def bind_tools(self, tools: List[BaseTool]) -> Any:
        """Bind tools to the LLM for function calling."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        self.model = model or settings.default_model
        self.temperature = temperature or settings.default_temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.api_key = api_key or settings.openai_api_key

        agent_logger.info(
            "Initializing OpenAI provider",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key,
            streaming=True,
        )

    async def agenerate(
        self, messages: List[BaseMessage], stream: bool = False, **kwargs
    ) -> Union[AsyncIterator[str], str]:
        """Generate response from messages."""
        if stream:
            return self._agenerate_stream(messages, **kwargs)
        else:
            response = await self.llm.ainvoke(messages, **kwargs)
            return response.content

    async def _agenerate_stream(
        self, messages: List[BaseMessage], **kwargs
    ) -> AsyncIterator[str]:
        """Generate streaming response."""
        async for chunk in self.llm.astream(messages, **kwargs):
            if chunk.content:
                yield chunk.content

    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model
    
    def bind_tools(self, tools: List[BaseTool]) -> ChatOpenAI:
        """Bind tools to the LLM for function calling."""
        # Return a new instance with tools bound. We only bind class-based tools here.
        return self.llm.bind_tools(tools)


class LLMFactory:
    """Factory for creating LLM providers."""

    _providers = {
        "openai": OpenAIProvider,
    }

    @classmethod
    def create(cls, provider: str = "openai", **kwargs) -> LLMProvider:
        """Create an LLM provider instance."""
        if provider not in cls._providers:
            raise ValueError(f"Unknown provider: {provider}")

        provider_class = cls._providers[provider]
        return provider_class(**kwargs)

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class
