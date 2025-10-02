from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

from agentsmithy_server.core.providers.model_spec import IModelSpec

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


# Perform autodiscovery once at import time
_autodiscover_models()

# PyInstaller onefile: pkgutil.iter_modules may return nothing inside the archive.
# Fallback to explicit imports if registry stayed empty (no runtime hooks required).
if not _MODEL_REGISTRY:
    try:
        # Keep this list in sync with available modules in this package
        for mod_name in (
            "gpt4_1",
            "gpt5",
            "gpt5_mini",
        ):
            importlib.import_module(f"{__name__}.{mod_name}")
    except Exception:
        # Best effort; validation layer will raise a clear error later
        pass

# Build supported chat models from registry after autodiscovery/fallback
SUPPORTED_OPENAI_CHAT_MODELS = set(_MODEL_REGISTRY.keys())


def get_model_spec(model: str) -> IModelSpec:
    """Factory that returns a spec instance for exact model name.
    Raises ValueError for unsupported names.
    """
    cls = _MODEL_REGISTRY.get(model)
    if not cls:
        raise ValueError(
            f"Unsupported OpenAI model '{model}'. Supported: {sorted(SUPPORTED_OPENAI_CHAT_MODELS)}"
        )
    return cls()
