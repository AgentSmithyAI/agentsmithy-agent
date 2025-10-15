"""Provider factory for automatic provider selection based on configuration."""

from __future__ import annotations

from typing import Any

from agentsmithy_server.config import settings
from agentsmithy_server.utils.logger import agent_logger


def create_provider(agent_name: str | None = None) -> Any:
    """Create LLM provider based on configuration.

    Selects provider based on:
    1. Agent-specific model configuration (models.agents.<agent_name>.model)
    2. Provider-specific configuration sections (providers.llama, providers.openai, etc.)
    3. Model name patterns (*.gguf -> llama, llama: prefix -> llama)
    4. Falls back to OpenAI provider

    Args:
        agent_name: Optional agent name for agent-specific configuration

    Returns:
        Configured provider instance (OpenAIProvider or LlamaProvider)
    """
    # Try to determine model/path from agent config
    agents_cfg = settings._get("models.agents", {})
    agent_model = None

    if isinstance(agents_cfg, dict):
        agent_entry = (
            agents_cfg.get(agent_name) if agent_name else agents_cfg.get("universal")
        )
        if isinstance(agent_entry, dict):
            agent_model = agent_entry.get("model")

    # Check for llama provider configuration
    llama_config = settings.get_provider_config("llama")
    llama_model_path = llama_config.get("model_path") if isinstance(llama_config, dict) else None

    # Decision logic: use llama if configured or model path looks like llama
    use_llama = False
    model_identifier = agent_model or settings.model

    # Check if llama is explicitly configured
    if llama_model_path:
        use_llama = True
        agent_logger.info(
            "Using Llama provider (configured in providers.llama)",
            model_path=llama_model_path,
        )
    # Check if agent/model name suggests llama
    elif model_identifier:
        if (
            isinstance(model_identifier, str)
            and (model_identifier.endswith(".gguf") or model_identifier.startswith("llama:"))
        ):
            use_llama = True
            agent_logger.info(
                "Using Llama provider (detected from model name pattern)",
                model=model_identifier,
            )

    # Ensure adapters are registered before creating any provider
    from agentsmithy_server.core.providers import register_builtin_adapters
    register_builtin_adapters()

    # Create the appropriate provider
    if use_llama:
        from agentsmithy_server.core.providers.llama.provider import LlamaProvider

        try:
            # Only pass agent_model if it looks like a llama model path
            llama_agent_model = None
            if agent_model and isinstance(agent_model, str):
                if agent_model.endswith(".gguf") or agent_model.startswith("llama:"):
                    llama_agent_model = agent_model
            
            # LlamaProvider will handle all config resolution internally
            return LlamaProvider(
                model_path=llama_agent_model,
                agent_name=agent_name,
            )
        except Exception as e:
            agent_logger.warning(
                "Failed to create Llama provider, falling back to OpenAI",
                error=str(e),
            )
            # Fall through to OpenAI provider

    # Default to OpenAI provider
    from agentsmithy_server.core.providers.openai.provider import OpenAIProvider

    agent_logger.info("Using OpenAI provider", agent_name=agent_name)
    return OpenAIProvider(agent_name=agent_name)

