"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import AsyncCallbackHandler
from agentsmithy_server.config import settings


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def agenerate(
        self, 
        messages: List[BaseMessage],
        stream: bool = False,
        **kwargs
    ) -> AsyncIterator[str] | str:
        """Generate response from messages."""
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider implementation."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None
    ):
        self.model = model or settings.default_model
        self.temperature = temperature or settings.default_temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.api_key = api_key or settings.openai_api_key
        
        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key,
            streaming=True
        )
    
    async def agenerate(
        self,
        messages: List[BaseMessage],
        stream: bool = False,
        **kwargs
    ) -> AsyncIterator[str] | str:
        """Generate response from messages."""
        if stream:
            async for chunk in self.llm.astream(messages, **kwargs):
                if chunk.content:
                    yield chunk.content
        else:
            response = await self.llm.ainvoke(messages, **kwargs)
            return response.content
    
    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model


class LLMFactory:
    """Factory for creating LLM providers."""
    
    _providers = {
        "openai": OpenAIProvider,
    }
    
    @classmethod
    def create(
        cls,
        provider: str = "openai",
        **kwargs
    ) -> LLMProvider:
        """Create an LLM provider instance."""
        if provider not in cls._providers:
            raise ValueError(f"Unknown provider: {provider}")
        
        provider_class = cls._providers[provider]
        return provider_class(**kwargs)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class 