from __future__ import annotations

from copy import deepcopy
from typing import Any

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


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy configuration keys to the current schema."""
    cfg = deepcopy(config)

    providers = cfg.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        cfg["providers"] = providers

    workloads = cfg.get("workloads")
    if not isinstance(workloads, dict):
        workloads = {}
        cfg["workloads"] = workloads

    models = cfg.get("models")
    if not isinstance(models, dict):
        models = {}
        cfg["models"] = models

    legacy_provider_keys: list[str] = []
    for name, provider_cfg in list(providers.items()):
        if not isinstance(provider_cfg, dict):
            legacy_provider_keys.append(name)
            continue

        has_credentials = bool(
            provider_cfg.get("api_key") or provider_cfg.get("base_url")
        )
        is_placeholder_model = "model" in provider_cfg and not has_credentials

        if is_placeholder_model:
            target_provider = provider_cfg.get("type") or Vendor.OPENAI.value
            if target_provider not in providers and Vendor.OPENAI.value in providers:
                target_provider = Vendor.OPENAI.value
            workload = workloads.setdefault(name, {})
            workload.setdefault("provider", target_provider)
            if "model" in provider_cfg and "model" not in workload:
                workload["model"] = provider_cfg["model"]
            if "options" in provider_cfg and "options" not in workload:
                workload["options"] = provider_cfg["options"]
            legacy_provider_keys.append(name)
        else:
            provider_cfg.setdefault("options", {})

    for key in legacy_provider_keys:
        providers.pop(key, None)

    for workload_cfg in workloads.values():
        if isinstance(workload_cfg, dict):
            workload_cfg.setdefault("options", {})

    def _normalize_model_entry(entry: Any) -> None:
        if not isinstance(entry, dict):
            return

        workload_name = entry.get("workload")
        provider_name = entry.get("provider")
        model_name = entry.get("model")
        entry_options = entry.get("options")

        if workload_name and not isinstance(workload_name, str):
            entry.pop("workload", None)
            workload_name = None

        if not workload_name and provider_name:
            workload_name = provider_name
            entry["workload"] = workload_name

        workload_cfg = None
        if workload_name:
            workload_cfg = workloads.setdefault(workload_name, {})
            if provider_name and "provider" not in workload_cfg:
                workload_cfg["provider"] = provider_name
            if model_name is not None and "model" not in workload_cfg:
                workload_cfg["model"] = model_name
            if entry_options is not None and "options" not in workload_cfg:
                workload_cfg["options"] = entry_options

        entry.pop("provider", None)
        entry.pop("model", None)
        entry.pop("options", None)

    agents = models.get("agents")
    if isinstance(agents, dict):
        for agent_cfg in agents.values():
            _normalize_model_entry(agent_cfg)

    for section in ("embeddings", "summarization"):
        section_cfg = models.get(section)
        if isinstance(section_cfg, dict):
            _normalize_model_entry(section_cfg)

    errors = validate_config_structure(cfg)
    if errors:
        raise ValueError("; ".join(errors))

    return cfg


def validate_config_structure(config: dict[str, Any]) -> list[str]:
    """Validate provider types and agent provider references."""
    errors: list[str] = []

    providers = config.get("providers") or {}
    available_providers = set(providers.keys())
    workloads = config.get("workloads") or {}
    available_workloads = set(workloads.keys())

    for name, provider_cfg in providers.items():
        if not isinstance(provider_cfg, dict):
            errors.append(f"Provider '{name}' must be an object")
            continue
        provider_type = provider_cfg.get("type") or Vendor.OPENAI.value
        if provider_type not in ALLOWED_PROVIDER_TYPES:
            errors.append(
                f"Provider '{name}' has unsupported type '{provider_type}'. "
                f"Allowed: {', '.join(ALLOWED_PROVIDER_TYPES)}"
            )

    for workload_name, workload_cfg in workloads.items():
        if not isinstance(workload_cfg, dict):
            errors.append(f"Workload '{workload_name}' must be an object")
            continue
        provider_name = workload_cfg.get("provider")
        if provider_name and provider_name not in available_providers:
            errors.append(
                f"Workload '{workload_name}' references unknown provider '{provider_name}'. "
                f"Available providers: {', '.join(sorted(available_providers)) or 'none'}"
            )

    def _ensure_provider(path: str, provider_name: str | None) -> None:
        if provider_name and provider_name not in available_providers:
            errors.append(
                f"Reference to unknown provider '{provider_name}' at '{path}'. "
                f"Available providers: {', '.join(sorted(available_providers)) or 'none'}"
            )

    def _ensure_workload(path: str, workload_name: str | None) -> None:
        if workload_name and workload_name not in available_workloads:
            errors.append(
                f"Reference to unknown workload '{workload_name}' at '{path}'. "
                f"Available workloads: {', '.join(sorted(available_workloads)) or 'none'}"
            )

    models = config.get("models") or {}
    agents = models.get("agents") or {}
    if isinstance(agents, dict):
        for agent_name, agent_cfg in agents.items():
            if isinstance(agent_cfg, dict):
                provider_name = agent_cfg.get("provider")
                workload_name = agent_cfg.get("workload")
                path = f"models.agents.{agent_name}"
                if workload_name:
                    _ensure_workload(f"{path}.workload", workload_name)
                else:
                    if provider_name:
                        errors.append(
                            f"{path} must reference a workload instead of a provider"
                        )
                    else:
                        errors.append(f"{path} must reference a workload")

    embeddings_cfg = models.get("embeddings")
    if isinstance(embeddings_cfg, dict):
        if embeddings_cfg.get("workload"):
            _ensure_workload(
                "models.embeddings.workload", embeddings_cfg.get("workload")
            )
        else:
            if embeddings_cfg.get("provider"):
                errors.append("models.embeddings must reference a workload")
            else:
                errors.append("models.embeddings must reference a workload")

    summarization_cfg = models.get("summarization")
    if isinstance(summarization_cfg, dict):
        if summarization_cfg.get("workload"):
            _ensure_workload(
                "models.summarization.workload",
                summarization_cfg.get("workload"),
            )
        else:
            if summarization_cfg.get("provider"):
                errors.append("models.summarization must reference a workload")
            else:
                errors.append("models.summarization must reference a workload")

    return errors


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
