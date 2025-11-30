from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agentsmithy.llm.providers.types import Vendor

ALLOWED_PROVIDER_TYPES: list[str] = [vendor.value for vendor in Vendor]


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge updates into base without mutating inputs.

    - Keys present in updates with non-None values are merged/overwritten
    - Keys present in updates with None values are skipped (preserve base value)
    - Keys not present in updates are preserved from base
    """
    result = deepcopy(base)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif key in result and value is None:
            # Treat None as "not provided" so lower layers keep their values
            continue
        else:
            result[key] = value
    return result


def apply_deletions(config: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit null deletions from updates to config.

    Recursively removes keys from config where updates has explicit None values.
    Used by API to handle {"providers": {"old-provider": null}} deletion requests.
    """
    result = deepcopy(config)
    for key, value in updates.items():
        if value is None:
            # Explicit None means "delete this key"
            result.pop(key, None)
        elif (
            isinstance(value, dict) and key in result and isinstance(result[key], dict)
        ):
            result[key] = apply_deletions(result[key], value)
    return result


def check_deletion_dependencies(
    current_config: dict[str, Any], updates: dict[str, Any]
) -> list[str]:
    """Check if deletions would break dependencies. Returns list of errors.

    Checks:
    - Deleting a provider that is referenced by workloads
    - Deleting a workload that is referenced by models.agents/embeddings/summarization
    """
    errors = []

    # Get what's being deleted
    providers_updates = updates.get("providers", {})
    workloads_updates = updates.get("workloads", {})

    if not isinstance(providers_updates, dict):
        providers_updates = {}
    if not isinstance(workloads_updates, dict):
        workloads_updates = {}

    # Find providers being deleted (value is None)
    deleting_providers = {k for k, v in providers_updates.items() if v is None}

    # Find workloads being deleted
    deleting_workloads = {k for k, v in workloads_updates.items() if v is None}

    # Check provider dependencies
    if deleting_providers:
        current_workloads = current_config.get("workloads", {})
        # Also consider workloads being updated (they might change provider reference)
        merged_workloads = deep_merge(current_workloads, workloads_updates)
        merged_workloads = apply_deletions(merged_workloads, workloads_updates)

        for provider_name in deleting_providers:
            referencing_workloads = []
            for wl_name, wl_config in merged_workloads.items():
                if (
                    isinstance(wl_config, dict)
                    and wl_config.get("provider") == provider_name
                ):
                    referencing_workloads.append(wl_name)
            if referencing_workloads:
                errors.append(
                    f"Cannot delete provider '{provider_name}': "
                    f"referenced by workloads: {', '.join(sorted(referencing_workloads))}"
                )

    # Check workload dependencies
    if deleting_workloads:
        current_models = current_config.get("models", {})
        # Consider models being updated too
        models_updates = updates.get("models", {})
        if not isinstance(models_updates, dict):
            models_updates = {}
        merged_models = deep_merge(current_models, models_updates)
        merged_models = apply_deletions(merged_models, models_updates)

        for workload_name in deleting_workloads:
            references = []

            # Check agents
            agents = merged_models.get("agents", {})
            if isinstance(agents, dict):
                for agent_name, agent_cfg in agents.items():
                    if (
                        isinstance(agent_cfg, dict)
                        and agent_cfg.get("workload") == workload_name
                    ):
                        references.append(f"models.agents.{agent_name}")

            # Check embeddings
            embeddings = merged_models.get("embeddings", {})
            if (
                isinstance(embeddings, dict)
                and embeddings.get("workload") == workload_name
            ):
                references.append("models.embeddings")

            # Check summarization
            summarization = merged_models.get("summarization", {})
            if (
                isinstance(summarization, dict)
                and summarization.get("workload") == workload_name
            ):
                references.append("models.summarization")

            if references:
                errors.append(
                    f"Cannot delete workload '{workload_name}': "
                    f"referenced by: {', '.join(sorted(references))}"
                )

    return errors


def rename_entity(
    config: dict[str, Any],
    entity_type: str,
    old_name: str,
    new_name: str,
) -> tuple[dict[str, Any], list[str]]:
    """Rename a workload or provider and update all references.

    Args:
        config: Current configuration dictionary
        entity_type: "workload" or "provider"
        old_name: Current name of the entity
        new_name: New name for the entity

    Returns:
        Tuple of (new_config, list_of_updated_references)

    Raises:
        ValueError: If entity doesn't exist or new name already exists
    """
    new_config = deepcopy(config)
    updated_refs: list[str] = []

    if entity_type == "workload":
        workloads = new_config.get("workloads", {})

        if old_name not in workloads:
            raise ValueError(f"Workload '{old_name}' not found")
        if new_name in workloads:
            raise ValueError(f"Workload '{new_name}' already exists")

        # Copy workload config to new name
        workloads[new_name] = workloads.pop(old_name)

        # Update all references in models
        models = new_config.get("models", {})

        # Check agents
        agents = models.get("agents", {})
        if isinstance(agents, dict):
            for agent_name, agent_cfg in agents.items():
                if (
                    isinstance(agent_cfg, dict)
                    and agent_cfg.get("workload") == old_name
                ):
                    agent_cfg["workload"] = new_name
                    updated_refs.append(f"models.agents.{agent_name}.workload")

        # Check embeddings
        embeddings = models.get("embeddings", {})
        if isinstance(embeddings, dict) and embeddings.get("workload") == old_name:
            embeddings["workload"] = new_name
            updated_refs.append("models.embeddings.workload")

        # Check summarization
        summarization = models.get("summarization", {})
        if (
            isinstance(summarization, dict)
            and summarization.get("workload") == old_name
        ):
            summarization["workload"] = new_name
            updated_refs.append("models.summarization.workload")

    elif entity_type == "provider":
        providers = new_config.get("providers", {})

        if old_name not in providers:
            raise ValueError(f"Provider '{old_name}' not found")
        if new_name in providers:
            raise ValueError(f"Provider '{new_name}' already exists")

        # Copy provider config to new name
        providers[new_name] = providers.pop(old_name)

        # Update all workloads that reference this provider
        workloads = new_config.get("workloads", {})
        for wl_name, wl_cfg in workloads.items():
            if isinstance(wl_cfg, dict) and wl_cfg.get("provider") == old_name:
                wl_cfg["provider"] = new_name
                updated_refs.append(f"workloads.{wl_name}.provider")

    else:
        raise ValueError(f"Invalid entity_type: {entity_type}")

    return new_config, updated_refs


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
    kind: Literal["chat", "embeddings"] | None = None  # None = auto-detect
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
    summary_trigger_token_budget: int = 20000
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


class ConfigValidationError(Exception):
    """Structured configuration validation error."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate configuration using Pydantic schema.

    Raises:
        ConfigValidationError: With structured list of human-readable error messages.
    """
    try:
        # Parse and validate using Pydantic
        # This handles type checking, defaults, and stripping unknown fields (extra='ignore')
        app_config = AppConfig.model_validate(config)

        # Return as dict for compatibility with existing code
        return app_config.model_dump(mode="json")
    except ValidationError as e:
        # Extract human-readable errors from Pydantic ValidationError
        errors = _extract_validation_errors(e)
        raise ConfigValidationError(errors) from e
    except ValueError as e:
        # Our own ValueError from check_referential_integrity
        # Already contains semicolon-separated messages
        errors = [err.strip() for err in str(e).split(";") if err.strip()]
        raise ConfigValidationError(errors) from e


def _extract_validation_errors(exc: ValidationError) -> list[str]:
    """Convert Pydantic ValidationError to list of human-readable messages."""
    errors = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) if err["loc"] else "config"
        msg = err["msg"]

        # Strip Pydantic's "Value error, " prefix from our custom messages
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]

        # Handle our custom ValueError messages from check_referential_integrity
        if err["type"] == "value_error" and ("Workload" in msg or "Provider" in msg):
            # Already a good message from our validator
            errors.append(msg)
        elif err["type"] == "missing":
            errors.append(f"Missing required field: {loc}")
        elif err["type"] == "string_type":
            errors.append(f"Expected string at '{loc}'")
        elif err["type"] == "int_type":
            errors.append(f"Expected integer at '{loc}'")
        elif err["type"] == "bool_type":
            errors.append(f"Expected boolean at '{loc}'")
        elif err["type"] == "dict_type":
            errors.append(f"Expected object at '{loc}'")
        else:
            # Generic fallback - still human readable
            errors.append(f"{loc}: {msg}")

    return errors if errors else ["Invalid configuration"]


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

        # Determine kind: use explicit value or infer from model name
        explicit_kind = workload_cfg.get("kind")
        if explicit_kind is not None:
            kind = explicit_kind
        else:
            # Auto-detect from model name
            from agentsmithy.llm.providers.known_models import infer_workload_kind

            model = workload_cfg.get("model")
            provider_name = workload_cfg.get("provider")
            # Get vendor type from provider config
            vendor = None
            if provider_name and provider_name in providers:
                provider_cfg = providers[provider_name]
                if isinstance(provider_cfg, dict):
                    vendor = provider_cfg.get("type")
            kind = infer_workload_kind(model, vendor)

        workload_meta.append(
            {
                "name": name,
                "provider": workload_cfg.get("provider"),
                "model": workload_cfg.get("model"),
                "kind": kind,
            }
        )

    return {
        "provider_types": ALLOWED_PROVIDER_TYPES,
        "providers": provider_meta,
        "agent_provider_slots": agent_slots,
        "workloads": workload_meta,
        "model_catalog": _build_model_catalog(providers),
    }


def _build_model_catalog(providers: dict[str, Any]) -> dict[str, Any]:
    """Return supported models grouped by provider/vendor.

    Delegates to registered catalog providers for each vendor.

    Args:
        providers: Provider configurations from config, used for
                   dynamic model discovery (e.g., Ollama base_url).
    """
    from agentsmithy.llm.providers import register_builtin_catalog_providers
    from agentsmithy.llm.providers.catalog import build_full_model_catalog

    # Ensure catalog providers are registered
    register_builtin_catalog_providers()

    return build_full_model_catalog(providers)
