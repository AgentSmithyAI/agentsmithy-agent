from __future__ import annotations

import inspect
import pkgutil
from collections.abc import Iterable
from importlib import import_module
from types import ModuleType

from .base_tool import BaseTool
from .registry import ToolRegistry


def _iter_tool_classes(mod: ModuleType) -> Iterable[type[BaseTool]]:
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        try:
            if issubclass(obj, BaseTool) and obj is not BaseTool:
                yield obj
        except Exception:
            continue


def build_registry(
    include: set[str] | None = None, exclude: set[str] | None = None
) -> ToolRegistry:
    registry = ToolRegistry()

    include = include or set()
    exclude = exclude or set()

    # Autodiscover tools from builtin package
    package_name = "agentsmithy_server.tools.builtin"
    pkg = import_module(package_name)

    for modinfo in pkgutil.iter_modules(pkg.__path__, package_name + "."):
        try:
            mod = import_module(modinfo.name)
        except Exception:
            continue

        for tool_cls in _iter_tool_classes(mod):
            tool_name = getattr(tool_cls, "name", tool_cls.__name__.lower())
            if include and tool_name not in include:
                continue
            if tool_name in exclude:
                continue
            try:
                registry.register(tool_cls())
            except Exception:
                continue

    return registry
