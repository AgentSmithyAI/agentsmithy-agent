from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a specific agent.

    Extend with temperature, tools policy, etc. as needed.
    """

    model: str  # No default - must be set explicitly
    temperature: float = 0.7


class AgentConfigProvider(Protocol):
    """Interface for pluggable agent configuration providers."""

    def get_config(self, agent_name: str) -> AgentConfig:  # pragma: no cover
        ...


class DefaultAgentConfigProvider:
    """Default provider; reads from env or uses sensible defaults.

    Env overrides:
      - AGENT_MODEL_<AGENT_NAME> (e.g., AGENT_MODEL_UNIVERSAL_AGENT)
      - AGENT_TEMPERATURE_<AGENT_NAME>
      - AGENT_DEFAULT_MODEL (fallback for all agents)
      - AGENT_DEFAULT_TEMPERATURE
    Names are case-insensitive; we uppercase agent_name for lookup.
    """

    def get_config(self, agent_name: str) -> AgentConfig:
        from agentsmithy_server.config import settings
        
        key = (agent_name or "").upper()
        default_model = os.getenv("AGENT_DEFAULT_MODEL", settings.default_model)
        default_temp = float(os.getenv("AGENT_DEFAULT_TEMPERATURE", "0.7"))

        model = os.getenv(f"AGENT_MODEL_{key}", default_model)
        try:
            temperature = float(
                os.getenv(f"AGENT_TEMPERATURE_{key}", str(default_temp))
            )
        except ValueError:
            temperature = default_temp
        return AgentConfig(model=model, temperature=temperature)


_provider_singleton: AgentConfigProvider | None = None


def get_agent_config_provider() -> AgentConfigProvider:
    global _provider_singleton
    if _provider_singleton is None:
        _provider_singleton = DefaultAgentConfigProvider()
    return _provider_singleton


def set_agent_config_provider(provider: AgentConfigProvider) -> None:
    global _provider_singleton
    _provider_singleton = provider
