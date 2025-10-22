from __future__ import annotations

from collections.abc import Callable

from .base_adapter import IProviderChatAdapter

# Factory signature: (model: str) -> Optional[IProviderChatAdapter]
_AdapterFactory = Callable[[str], IProviderChatAdapter | None]

_REGISTRY: list[_AdapterFactory] = []


def register_adapter_factory(factory: _AdapterFactory) -> None:
    """Register an adapter factory with priority order (first match wins).

    Idempotent: the same factory object will not be added twice.
    """
    if factory not in _REGISTRY:
        _REGISTRY.append(factory)


def clear_registry() -> None:
    _REGISTRY.clear()


def get_adapter(model: str) -> IProviderChatAdapter:
    """Resolve an adapter for a given model by trying registered factories."""
    for factory in _REGISTRY:
        adapter = factory(model)
        if adapter is not None:
            return adapter
    raise ValueError(f"No provider adapter found for model '{model}'")
