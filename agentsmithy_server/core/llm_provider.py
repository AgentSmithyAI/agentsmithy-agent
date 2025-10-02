"""LLM Provider abstraction for flexible model integration."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from importlib import import_module
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from agentsmithy_server.config import settings
from agentsmithy_server.core.providers import register_builtin_adapters
from agentsmithy_server.core.providers.openai.models import get_model_spec
from agentsmithy_server.core.providers.registry import get_adapter
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
        self.model = model or settings.model
        self.temperature = temperature or settings.temperature
        self.max_tokens = max_tokens or settings.max_tokens
        self.api_key = api_key or settings.openai_api_key

        # Validate that model is set
        if not self.model:
            raise ValueError(
                "LLM model not specified. Please set 'model' in "
                ".agentsmithy/config.json or pass model parameter explicitly"
            )

        agent_logger.info(
            "Initializing OpenAI provider",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Ensure adapters are registered (no import side-effects)
        register_builtin_adapters()
        # Resolve provider adapter via registry
        adapter = get_adapter(self.model)
        class_path, kwargs = adapter.build_langchain(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=settings.reasoning_effort,
        )

        # Initialize LLM; use explicit API key if provided
        if self.api_key:

            # Map vendor -> env var via central helper
            from agentsmithy_server.core.providers.vendor import set_api_key_env

            vendor = adapter.vendor() if hasattr(adapter, "vendor") else None
            if vendor is not None:
                set_api_key_env(vendor, str(self.api_key))

        module_path, class_name = class_path.rsplit(".", 1)
        cls = getattr(import_module(module_path), class_name)
        try:
            agent_logger.debug(
                "Initializing chat model",
                class_path=class_path,
                kwargs_keys=list(kwargs.keys()),
            )
        except Exception:
            pass
        self.llm = cls(**kwargs)

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

            # Track usage information from chunks
            try:
                # Check for usage in various locations where providers might put it
                usage = None
                add = getattr(chunk, "additional_kwargs", {}) or {}
                if isinstance(add, dict) and add.get("usage"):
                    usage = add.get("usage")

                meta = getattr(chunk, "response_metadata", {}) or {}
                if not usage and isinstance(meta, dict) and meta.get("token_usage"):
                    usage = meta.get("token_usage")

                # Direct usage_metadata attribute (preferred)
                um = getattr(chunk, "usage_metadata", None)
                if isinstance(um, dict) and um:
                    usage = um

                if usage:
                    self._last_usage = usage
            except Exception:
                pass

    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model

    def bind_tools(self, tools: list[BaseTool]) -> Any:
        """Bind tools to the LLM for function calling."""
        # Return a tool-bound runnable/LLM as provided by SDK
        return self.llm.bind_tools(tools)

    def get_last_usage(self) -> dict[str, Any] | None:
        """Return last observed usage from streaming; may be None if unavailable."""
        return self._last_usage

    def get_stream_kwargs(self) -> dict[str, Any]:
        """Return vendor-specific kwargs for astream() calls.

        For chat_completions family: include stream_usage=True
        For responses family (gpt-5/gpt-5-mini): no stream_usage (unsupported)
        """
        # Prefer adapter's stream kwargs when available; fallback to OpenAI heuristic
        try:
            adapter = get_adapter(self.model)
            return adapter.stream_kwargs()
        except Exception:
            pass
        family = getattr(get_model_spec(self.model), "family", "chat_completions")
        if family == "responses":
            return {}
        return {"stream_usage": True}


# Note: Historical LLMFactory was removed. Instantiate providers directly,
# e.g., OpenAIProvider(...). Factory indirection is unnecessary because
# provider resolution happens via the model adapter registry.
