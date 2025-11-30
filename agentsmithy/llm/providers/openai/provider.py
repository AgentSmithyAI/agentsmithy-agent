"""OpenAI provider implementation for chat models.

This module contains `OpenAIProvider`, extracted from `agentsmithy.core.llm_provider`
to live under the OpenAI provider package. It preserves the same public API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from agentsmithy.config import settings
from agentsmithy.domain.events import EventType
from agentsmithy.llm.providers import register_builtin_adapters
from agentsmithy.llm.providers.openai.models import get_model_spec
from agentsmithy.llm.providers.registry import get_adapter
from agentsmithy.llm.providers.types import Vendor
from agentsmithy.utils.logger import agent_logger

DEFAULT_CHAT_TEMPERATURE = 0.7
DEFAULT_CHAT_MAX_TOKENS = 4000
DEFAULT_REASONING_EFFORT = "low"


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
        # Agent model selection via models.agents or models.summarization
        if agent_name == "summarization":
            agent_entry = settings._get("models.summarization", None)
        else:
            if not agent_name:
                agent_name = "universal"
            agents_cfg = settings._get("models.agents", None)
            if not isinstance(agents_cfg, dict):
                raise ValueError(
                    "models.agents configuration not found. "
                    "Check models.agents in your config."
                )
            agent_entry = agents_cfg.get(agent_name)

        # Resolve workload -> provider chain (NO silent fallbacks!)
        # Structure: models.agents.universal.workload -> workloads.<name>.provider -> providers.<name>
        if not isinstance(agent_entry, dict):
            raise ValueError(
                f"Agent configuration not found for '{agent_name or 'universal'}'. "
                f"Check models.agents.{agent_name or 'universal'} in your config."
            )

        workload_name = agent_entry.get("workload")
        if not workload_name:
            raise ValueError(
                f"Agent '{agent_name or 'universal'}' has no workload specified. "
                f"Set models.agents.{agent_name or 'universal'}.workload in your config."
            )

        workload_config = settings._get_workload_config(workload_name)
        if not isinstance(workload_config, dict):
            raise ValueError(
                f"Workload '{workload_name}' not found in configuration. "
                f"Check workloads.{workload_name} in your config."
            )

        provider_name = workload_config.get("provider")
        if not provider_name:
            raise ValueError(
                f"Workload '{workload_name}' has no provider specified. "
                f"Set workloads.{workload_name}.provider in your config."
            )

        provider_def = settings._get(f"providers.{provider_name}", None)
        if not isinstance(provider_def, dict):
            raise ValueError(
                f"Provider '{provider_name}' not found in configuration. "
                f"Check providers.{provider_name} in your config."
            )

        # Resolve model, api_key, base_url from configuration
        resolved_model = workload_config.get("model") or provider_def.get("model")
        resolved_api_key = provider_def.get("api_key")
        resolved_base_url = provider_def.get("base_url")
        resolved_options = provider_def.get("options", {})
        provider_type = provider_def.get("type", Vendor.OPENAI.value)

        # Apply explicit parameters (constructor args override config)
        final_model = model or resolved_model
        if not final_model:
            raise ValueError(
                "LLM model not specified. Configure workloads.<name>.model "
                "or providers.<name>.model in your config."
            )

        self.model: str = final_model
        self.api_key = api_key or resolved_api_key
        self.base_url = base_url or resolved_base_url
        self.provider_options = (
            resolved_options if isinstance(resolved_options, dict) else {}
        )

        # Temperature and max_tokens use explicit or defaults
        self.temperature = (
            temperature if temperature is not None else DEFAULT_CHAT_TEMPERATURE
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else DEFAULT_CHAT_MAX_TOKENS
        )

        agent_logger.info(
            "Initializing LLM provider",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            base_url=self.base_url,
            provider=provider_name,
            provider_type=provider_type,
        )

        # Get adapter based on provider type
        from agentsmithy.llm.providers.base_adapter import IProviderChatAdapter

        adapter: IProviderChatAdapter
        if provider_type == Vendor.OLLAMA.value:
            # Ollama: use dedicated adapter without stream_options
            from agentsmithy.llm.providers.ollama.adapter import create_ollama_adapter

            adapter = create_ollama_adapter(self.model)
        else:
            # OpenAI and compatible: use registry-based adapter resolution
            register_builtin_adapters()
            adapter = get_adapter(self.model)

        # Store adapter for get_stream_kwargs()
        self._adapter = adapter

        class_path, kwargs = adapter.build_langchain(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        )

        # Apply extended per-model options from provider config
        extra_opts = self.provider_options
        if isinstance(extra_opts, dict) and extra_opts:
            if provider_type == Vendor.OLLAMA.value:
                # Ollama: merge into model_kwargs (chat_completions style)
                if "model_kwargs" not in kwargs or not isinstance(
                    kwargs.get("model_kwargs"), dict
                ):
                    kwargs["model_kwargs"] = {}
                kwargs["model_kwargs"].update(extra_opts)
            else:
                # OpenAI: check model family
                model_spec = get_model_spec(self.model)
                family = getattr(model_spec, "family", "chat_completions")
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

        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key

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
                yield {"type": EventType.CHAT.value, "content": content}

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

        For OpenAI chat_completions: include stream_usage=True
        For OpenAI responses family: no stream_usage (unsupported)
        For Ollama: no stream_usage (unsupported)
        """
        return self._adapter.stream_kwargs()
