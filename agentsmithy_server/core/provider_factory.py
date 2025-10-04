"""Provider factory for creating LLM providers with automatic configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentsmithy_server.config import settings
from agentsmithy_server.core.llm_provider import OpenAIProvider
from agentsmithy_server.core.providers import register_builtin_adapters
from agentsmithy_server.core.providers.registry import get_adapter
from agentsmithy_server.core.providers.types import Vendor
from agentsmithy_server.utils.logger import get_logger

if TYPE_CHECKING:
    from agentsmithy_server.core.llm_provider import LLMProvider

logger = get_logger("provider_factory")


def _cast_config_value(value: Any, expected_type: type) -> Any:
    """Cast config value to expected type if needed.

    Args:
        value: Value from config (could be str, int, float, None, etc.)
        expected_type: Expected type (float, int, str)

    Returns:
        Value cast to expected type, or None if value is None
    """
    if value is None:
        return None
    if isinstance(value, expected_type):
        return value
    return expected_type(value)


def create_provider_for_model(
    model: str,
    agent_name: str | None = None,
) -> LLMProvider:
    """Create LLM provider for a given model with automatic configuration.

    Args:
        model: Model name (e.g., "gpt-5", "gpt-5-mini", "granite-3.1-8b-instruct")
        agent_name: Optional agent name for logging

    Returns:
        Configured LLM provider instance

    The function:
    1. Determines the provider vendor from the model using the adapter registry
    2. Looks up provider configuration from settings.providers[vendor]
    3. Creates and configures the appropriate provider
    """
    # Ensure adapters are registered
    register_builtin_adapters()

    # Determine vendor from model via adapter registry
    try:
        adapter = get_adapter(model)
        vendor = adapter.vendor()
    except ValueError as e:
        logger.error("No adapter found for model", model=model, error=str(e))
        raise ValueError(
            f"Model '{model}' is not supported. No adapter registered for this model."
        ) from e

    # Map vendor to provider config section name
    provider_config_name = _vendor_to_config_name(vendor)

    # Get provider configuration from settings
    provider_config = settings.get_provider_config(provider_config_name)

    # Merge with legacy settings for backwards compatibility
    if not provider_config or not provider_config.get("api_key"):
        # Fallback to legacy settings
        legacy_api_key = settings.openai_api_key
        legacy_base_url = settings.openai_base_url
        legacy_temperature = settings.temperature
        legacy_max_tokens = settings.max_tokens

        if not provider_config:
            provider_config = {}

        if not provider_config.get("api_key") and legacy_api_key:
            provider_config["api_key"] = legacy_api_key
        if not provider_config.get("base_url") and legacy_base_url:
            provider_config["base_url"] = legacy_base_url
        if not provider_config.get("temperature"):
            provider_config["temperature"] = legacy_temperature
        if not provider_config.get("max_tokens"):
            provider_config["max_tokens"] = legacy_max_tokens

    # For llama provider, ensure we have a dummy api_key (ChatOpenAI requires it)
    if vendor == Vendor.OTHER and provider_config.get("api_key") is None:
        provider_config = dict(
            provider_config
        )  # Make a copy to avoid mutating original
        provider_config["api_key"] = "not-needed"

    logger.info(
        "Creating provider for model",
        model=model,
        vendor=vendor,
        provider_config_name=provider_config_name,
        agent_name=agent_name,
        has_api_key=bool(provider_config.get("api_key")),
        base_url=provider_config.get("base_url"),
    )

    # Create provider based on vendor
    # Currently, we only have OpenAIProvider which handles OpenAI-compatible APIs
    return OpenAIProvider(
        model=model,
        temperature=_cast_config_value(provider_config.get("temperature"), float),
        max_tokens=_cast_config_value(provider_config.get("max_tokens"), int),
        api_key=_cast_config_value(provider_config.get("api_key"), str),
        base_url=_cast_config_value(provider_config.get("base_url"), str),
        agent_name=agent_name,
    )


def create_provider_for_agent(agent_name: str) -> LLMProvider:
    """Create LLM provider for a specific agent using its configured model.

    Args:
        agent_name: Agent name (e.g., "inspector", "universal")

    Returns:
        Configured LLM provider instance

    The function:
    1. Looks up the agent's model from settings.agents[agent_name].model
    2. Falls back to legacy settings.model if not configured
    3. Calls create_provider_for_model with the resolved model
    """
    # Get model for agent from config
    model = settings.get_agent_model(agent_name)

    # Fallback to legacy model setting
    if not model:
        model = settings.model
        logger.debug(
            "No model configured for agent, using legacy model setting",
            agent_name=agent_name,
            model=model,
        )

    if not model:
        raise ValueError(
            f"No model configured for agent '{agent_name}'. "
            "Please set 'agents.{agent_name}.model' in config or 'model' setting."
        )

    return create_provider_for_model(model, agent_name=agent_name)


def _vendor_to_config_name(vendor: Vendor) -> str:
    """Map vendor enum to config section name."""
    vendor_map = {
        Vendor.OPENAI: "openai",
        Vendor.ANTHROPIC: "anthropic",
        Vendor.XAI: "xai",
        Vendor.DEEPSEEK: "deepseek",
        Vendor.OTHER: "llama",  # Map OTHER to "llama" config section
    }
    return vendor_map.get(vendor, "openai")
