from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentsmithy.llm.providers.types import Vendor

ALLOWED_PROVIDER_TYPES: list[str] = [vendor.value for vendor in Vendor]


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge updates into base without mutating inputs."""
    result = deepcopy(base)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ProviderConfig(BaseModel):
    type: str = "openai"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class WorkloadConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class AgentModelConfig(BaseModel):
    workload: str | None = None

    model_config = ConfigDict(extra="ignore")


class ModelsConfig(BaseModel):
    agents: dict[str, AgentModelConfig] = Field(default_factory=dict)
    embeddings: AgentModelConfig = Field(default_factory=AgentModelConfig)
    summarization: AgentModelConfig = Field(default_factory=AgentModelConfig)

    model_config = ConfigDict(extra="ignore")


class AppConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    workloads: dict[str, WorkloadConfig] = Field(default_factory=dict)
    models: ModelsConfig = Field(default_factory=ModelsConfig)

    server_host: str = "localhost"
    server_port: int = 8765
    chroma_persist_directory: str = "./chroma_db"
    max_context_length: int = 10000
    max_open_files: int = 5
    summary_trigger_token_budget: int = 20000
    streaming_enabled: bool = True
    web_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    log_level: str = "INFO"
    log_format: str = "pretty"
    log_colors: bool = True

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def check_referential_integrity(self) -> AppConfig:
        """Validate logical relationships between config sections."""
        available_providers = set(self.providers.keys())
        available_workloads = set(self.workloads.keys())
        errors = []

        # Validate provider types
        for name, provider in self.providers.items():
            if provider.type not in ALLOWED_PROVIDER_TYPES:
                errors.append(
                    f"Provider '{name}' has unsupported type '{provider.type}'. "
                    f"Allowed: {', '.join(ALLOWED_PROVIDER_TYPES)}"
                )

        # Validate workload references
        for name, workload in self.workloads.items():
            if workload.provider and workload.provider not in available_providers:
                errors.append(
                    f"Workload '{name}' references unknown provider '{workload.provider}'. "
                    f"Available providers: {', '.join(sorted(available_providers)) or 'none'}"
                )

        # Validate model references
        def _check_workload(path: str, workload_name: str | None) -> None:
            if workload_name and workload_name not in available_workloads:
                errors.append(
                    f"Reference to unknown workload '{workload_name}' at '{path}'. "
                    f"Available workloads: {', '.join(sorted(available_workloads)) or 'none'}"
                )

        # Check agents
        for name, agent in self.models.agents.items():
            _check_workload(f"models.agents.{name}.workload", agent.workload)

        # Check system models
        _check_workload("models.embeddings.workload", self.models.embeddings.workload)
        _check_workload(
            "models.summarization.workload", self.models.summarization.workload
        )

        if errors:
            raise ValueError("; ".join(errors))

        return self


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate configuration using Pydantic schema."""
    try:
        # Parse and validate using Pydantic
        # This handles type checking, defaults, and stripping unknown fields (extra='ignore')
        app_config = AppConfig.model_validate(config)

        # Return as dict for compatibility with existing code
        return app_config.model_dump(mode="json")
    except Exception as e:
        # Wrap Pydantic validation errors in ValueError for consistent error handling
        raise ValueError(str(e)) from e


def build_config_metadata(config: dict[str, Any]) -> dict[str, Any]:
    """Return metadata describing the configuration structure for clients."""
    providers = config.get("providers") or {}
    workloads = config.get("workloads") or {}
    provider_meta = []
    for name, provider_cfg in providers.items():
        if not isinstance(provider_cfg, dict):
            continue
        provider_meta.append(
            {
                "name": name,
                "type": provider_cfg.get("type") or Vendor.OPENAI.value,
                "has_api_key": bool(provider_cfg.get("api_key")),
                "model": provider_cfg.get("model"),
            }
        )

    agent_slots = []
    models = config.get("models") or {}
    agents = models.get("agents") or {}
    if isinstance(agents, dict):
        for agent_name, agent_cfg in agents.items():
            if isinstance(agent_cfg, dict):
                path = (
                    f"models.agents.{agent_name}.workload"
                    if "workload" in agent_cfg
                    else f"models.agents.{agent_name}.provider"
                )
                agent_slots.append(
                    {
                        "path": path,
                        "provider": agent_cfg.get("provider"),
                        "workload": agent_cfg.get("workload"),
                    }
                )

    for section in ("embeddings", "summarization"):
        section_cfg = models.get(section)
        if isinstance(section_cfg, dict):
            path = (
                f"models.{section}.workload"
                if "workload" in section_cfg
                else f"models.{section}.provider"
            )
            agent_slots.append(
                {
                    "path": path,
                    "provider": section_cfg.get("provider"),
                    "workload": section_cfg.get("workload"),
                }
            )

    workload_meta = []
    for name, workload_cfg in workloads.items():
        if not isinstance(workload_cfg, dict):
            continue
        workload_meta.append(
            {
                "name": name,
                "provider": workload_cfg.get("provider"),
                "model": workload_cfg.get("model"),
            }
        )

    return {
        "provider_types": ALLOWED_PROVIDER_TYPES,
        "providers": provider_meta,
        "agent_provider_slots": agent_slots,
        "workloads": workload_meta,
        "model_catalog": _build_model_catalog(),
    }


def _build_model_catalog() -> dict[str, Any]:
    """Return supported models grouped by provider/vendor."""
    catalog: dict[str, Any] = {}

    # OpenAI-compatible models (chat + embeddings)
    try:
        from agentsmithy.llm.providers.openai import models as openai_models

        catalog[Vendor.OPENAI.value] = {
            "chat": sorted(list(openai_models.SUPPORTED_OPENAI_CHAT_MODELS)),
            "embeddings": sorted(list(openai_models.SUPPORTED_OPENAI_EMBEDDING_MODELS)),
        }
    except Exception:
        catalog[Vendor.OPENAI.value] = {"chat": [], "embeddings": []}

    return catalog
