from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

from agentsmithy_server.llm.providers.model_spec import IModelSpec

from ._base import OpenAIModelSpec  # re-export for typing

# Internal registry populated via decorator when modules are imported
_MODEL_REGISTRY: dict[str, type[OpenAIModelSpec]] = {}


def register_model(
    name: str,
) -> Callable[[type[OpenAIModelSpec]], type[OpenAIModelSpec]]:
    """Class decorator to auto-register OpenAI model specs by exact name.

    Usage:
        @register_model("gpt-5")
        class GPT5Config(OpenAIModelSpec):
            ...
    """

    def _decorator(cls: type[OpenAIModelSpec]) -> type[OpenAIModelSpec]:
        # Persist mapping and set class attribute so base can infer name in __init__
        cls.model_name = name
        _MODEL_REGISTRY[name] = cls
        return cls

    return _decorator


# Embedding models remain an explicit allow-list (handled elsewhere)
SUPPORTED_OPENAI_EMBEDDING_MODELS = {
    "text-embedding-3-small",
    "text-embedding-3-large",
}


def _autodiscover_models() -> None:
    """Import all submodules to trigger @register_model decorators."""
    pkg_name = __name__
    pkg_path = __path__
    for mod in pkgutil.iter_modules(pkg_path):
        if mod.name.startswith("__"):
            continue
        importlib.import_module(f"{pkg_name}.{mod.name}")


# Perform autodiscovery once at import time (works in dev mode)
# In frozen mode, rthook will import modules explicitly
_autodiscover_models()


def __getattr__(name: str):
    """Lazy module attribute access.

    SUPPORTED_OPENAI_CHAT_MODELS is computed on-demand to ensure
    _MODEL_REGISTRY is fully populated by rthook imports before access.
    """
    if name == "SUPPORTED_OPENAI_CHAT_MODELS":
        return set(_MODEL_REGISTRY.keys())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_model_spec(model: str) -> IModelSpec:
    """Factory that returns a spec instance for exact model name.
    Raises ValueError for unsupported names.
    """
    cls = _MODEL_REGISTRY.get(model)
    if not cls:
        raise ValueError(
            f"Unsupported OpenAI model '{model}'. Supported: {sorted(_MODEL_REGISTRY.keys())}"
        )
    return cls()
