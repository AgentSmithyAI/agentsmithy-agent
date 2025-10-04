"""Providers package.

Exposes helper to register built-in provider adapters without side-effects.
"""

from .llama.adapter import factory as llama_factory
from .openai.adapter import factory as openai_factory
from .registry import register_adapter_factory


def register_builtin_adapters() -> None:
    """Register built-in adapters (idempotent).

    Order matters: first match wins.
    Register more specific adapters first, then fallbacks.
    """
    # Llama/self-hosted first (for granite models)
    register_adapter_factory(llama_factory)
    # OpenAI and cloud providers as fallback
    register_adapter_factory(openai_factory)
