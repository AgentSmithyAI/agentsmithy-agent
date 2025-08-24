"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agentsmithy_server.config import settings
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

        # Build extra provider-specific kwargs (e.g., GPT-5 reasoning controls)
        extra_model_kwargs: dict[str, Any] = {}
        # Pass GPT-5 reasoning controls only for GPT-5 models
        if isinstance(self.model, str) and self.model.startswith("gpt-5"):
            reasoning_kwargs: dict[str, Any] = {}
            # Always request a reasoning summary; default to 'auto' if not configured
            verbosity = getattr(settings, "reasoning_verbosity", None) or "auto"
            reasoning_kwargs["summary"] = verbosity
            # Include effort if configured
            effort = getattr(settings, "reasoning_effort", None)
            if effort:
                reasoning_kwargs["effort"] = effort
            extra_model_kwargs["reasoning"] = reasoning_kwargs

        # Determine whether to include temperature (unsupported on some models like gpt-5)
        def _supports_temperature(model_name: str) -> bool:
            try:
                # Disallow temperature for GPT-5 family (Responses API rejects it)
                if model_name.startswith("gpt-5"):
                    return False
            except Exception:
                pass
            return True

        # Assemble ChatOpenAI kwargs conditionally
        base_kwargs: dict[str, Any] = {
            "model": self.model,
            "streaming": True,
        }
        if _supports_temperature(self.model) and self.temperature is not None:
            base_kwargs["temperature"] = self.temperature
        # Route token limit to correct parameter depending on model family
        if isinstance(self.model, str) and self.model.startswith("gpt-5"):
            # Responses API expects max_output_tokens
            extra_model_kwargs["max_output_tokens"] = self.max_tokens
        else:
            base_kwargs["max_tokens"] = self.max_tokens
        if extra_model_kwargs:
            try:
                agent_logger.debug(
                    "OpenAI ChatOpenAI model_kwargs",
                    model=self.model,
                    model_kwargs=extra_model_kwargs,
                )
            except Exception:
                pass
            base_kwargs["model_kwargs"] = extra_model_kwargs

        # Initialize LLM; use explicit API key if provided
        if self.api_key:
            # Note: langchain_openai expects SecretStr; use environment variable fallback instead
            import os

            os.environ.setdefault("OPENAI_API_KEY", str(self.api_key))
            try:
                agent_logger.debug("Initializing ChatOpenAI", base_kwargs_keys=list(base_kwargs.keys()))
            except Exception:
                pass
            self.llm = ChatOpenAI(**base_kwargs)
        else:
            try:
                agent_logger.debug("Initializing ChatOpenAI", base_kwargs_keys=list(base_kwargs.keys()))
            except Exception:
                pass
            self.llm = ChatOpenAI(**base_kwargs)

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
                # Attach metadata if SDK provides it
                try:
                    response_meta = {
                        "response_metadata": getattr(chunk, "response_metadata", {})
                        or {},
                        "additional_kwargs": getattr(chunk, "additional_kwargs", {})
                        or {},
                    }
                except Exception:
                    response_meta = {}

                if response_meta and any(response_meta.values()):
                    yield {"content": content, "metadata": response_meta}
                else:
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
