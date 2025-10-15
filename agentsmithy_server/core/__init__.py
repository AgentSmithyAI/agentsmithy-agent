"""Core module for AgentSmithy server."""

from .llm_provider import LLMProvider
from .provider_factory import create_provider
from .providers.openai.provider import OpenAIProvider
from .providers.types import Vendor

# Lazy import to avoid circular dependency
def __getattr__(name):
    if name == "LlamaProvider":
        from .providers.llama.provider import LlamaProvider
        return LlamaProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "LLMProvider",
    "OpenAIProvider",
    "LlamaProvider",
    "Vendor",
    "create_provider",
]
