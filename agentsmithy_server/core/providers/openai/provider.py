"""OpenAI provider implementation for chat models.

This module contains `OpenAIProvider`, extracted from `agentsmithy_server.core.llm_provider`
to live under the OpenAI provider package. It preserves the same public API.
"""

from __future__ import annotations

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


class OpenAIProvider:
    """OpenAI LLM provider implementation.

    Implements the same interface as `LLMProvider` without inheriting directly
    to avoid circular imports at module load time.
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        agent_name: str | None = None,
    ):
        # Agent model selection via models.agents; default to universal unless agent_name given
        agents_cfg = settings._get("models.agents", {})
        if isinstance(agents_cfg, dict):
            agent_entry = (
                agents_cfg.get(agent_name)
                if agent_name
                else agents_cfg.get("universal")
            )
        else:
            agent_entry = None

        # Use explicit values or fall back to agent profile -> nested OpenAI chat -> global
        resolved_agent_model = (
            agent_entry.get("model") if isinstance(agent_entry, dict) else None
        )
        self.model = (
            model
            or resolved_agent_model
            or settings.openai_chat_model
            or settings.model
        )
        # Temperature and max_tokens are not in agent profile; use explicit or settings defaults
        self.temperature = (
            temperature if temperature is not None else settings.openai_chat_temperature
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else settings.openai_chat_max_tokens
        )

        # Provider credentials: prefer providers.openai, then openai section, then flat env
        prov_openai = settings.get_provider_config("openai")
        self.api_key = api_key or prov_openai.get("api_key") or settings.openai_api_key
        self.base_url = (
            base_url or prov_openai.get("base_url") or settings.openai_base_url
        )

        if not self.model:
            raise ValueError(
                "LLM model not specified. Set 'model' or configure openai.chat.model"
            )

        agent_logger.info(
            "Initializing OpenAI provider",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            base_url=self.base_url,
        )

        # Ensure adapters are registered (no import side-effects outside this call)
        register_builtin_adapters()
        adapter = get_adapter(self.model)
        class_path, kwargs = adapter.build_langchain(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=settings.reasoning_effort,
        )

        # Apply extended OpenAI per-model options from provider config (preferred)
        try:
            extra_opts = settings.openai_chat_options or {}
            if isinstance(extra_opts, dict) and extra_opts:
                family = getattr(
                    get_model_spec(self.model), "family", "chat_completions"
                )
                if family == "responses":
                    # Responses API: top-level kwargs
                    kwargs.update(extra_opts)
                else:
                    # Chat Completions: merge into model_kwargs
                    if "model_kwargs" not in kwargs or not isinstance(
                        kwargs.get("model_kwargs"), dict
                    ):
                        kwargs["model_kwargs"] = {}
                    kwargs["model_kwargs"].update(extra_opts)
        except Exception:
            # Be lenient if options cannot be applied
            pass

        # Initialize LLM; set API key env var for this vendor when provided
        if self.api_key:
            from agentsmithy_server.core.providers.vendor import set_api_key_env

            vendor = adapter.vendor() if hasattr(adapter, "vendor") else None
            if vendor is not None:
                set_api_key_env(vendor, str(self.api_key))

        if self.base_url:
            kwargs["base_url"] = self.base_url

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
            return str(content)

    async def _agenerate_stream(
        self, messages: list[BaseMessage], **kwargs
    ) -> AsyncIterator[str | dict[str, Any]]:
        """Generate streaming response."""
        async for chunk in self.llm.astream(messages, **kwargs):
            content = getattr(chunk, "content", None)
            if isinstance(content, str) and content:
                yield {"type": "chat", "content": content}

            # Track usage information from chunks, tolerant of provider differences
            try:
                usage = None
                add = getattr(chunk, "additional_kwargs", {}) or {}
                if isinstance(add, dict) and add.get("usage"):
                    usage = add.get("usage")

                meta = getattr(chunk, "response_metadata", {}) or {}
                if not usage and isinstance(meta, dict) and meta.get("token_usage"):
                    usage = meta.get("token_usage")

                um = getattr(chunk, "usage_metadata", None)
                if isinstance(um, dict) and um:
                    usage = um

                if usage:
                    self._last_usage = usage
            except Exception:
                pass

    def get_model_name(self) -> str:
        return self.model

    def bind_tools(self, tools: list[BaseTool]) -> Any:
        return self.llm.bind_tools(tools)

    def get_last_usage(self) -> dict[str, Any] | None:
        return self._last_usage

    def get_stream_kwargs(self) -> dict[str, Any]:
        """Return vendor-specific kwargs for astream() calls.

        For chat_completions family: include stream_usage=True
        For responses family (gpt-5/gpt-5-mini): no stream_usage (unsupported)
        """
        try:
            adapter = get_adapter(self.model)
            return adapter.stream_kwargs()
        except Exception:
            pass
        family = getattr(get_model_spec(self.model), "family", "chat_completions")
        if family == "responses":
            return {}
        return {"stream_usage": True}
