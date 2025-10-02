from __future__ import annotations

from collections.abc import Callable

from ._base import OpenAIModelSpec

# Internal registry populated via decorator when modules are imported
_MODEL_REGISTRY: dict[str, type[OpenAIModelSpec]] = {}


def register_model(
    name: str,
) -> Callable[[type[OpenAIModelSpec]], type[OpenAIModelSpec]]:
    """Class decorator to auto-register OpenAI model specs by exact name."""

    def _decorator(cls: type[OpenAIModelSpec]) -> type[OpenAIModelSpec]:
        _MODEL_REGISTRY[name] = cls
        return cls

    return _decorator
