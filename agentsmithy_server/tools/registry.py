"""Registry module for tools and summary registration.

- Exposes ToolRegistry (manager for tool instances)
- Hosts SUMMARY_REGISTRY (by name) and CLASS_SUMMARY_REGISTRY (by class)
- Provides decorators:
  - register_summary(name: str)
  - register_summaries(*names: str)
  - register_summary_for(*tool_classes: type[BaseTool])  [preferred]
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from langchain_core.tools import BaseTool as LCBaseTool

from .base_tool import BaseTool
from .tool_manager import ToolManager

# Generic summary function signature: (args, result) -> str
SummaryFunc = Callable[[dict[str, Any], dict[str, Any]], str]

# Primary lookup used at runtime by tool name (kept for compatibility)
SUMMARY_REGISTRY: dict[str, SummaryFunc] = {}

# Optional lookup by concrete tool class for better typing/ergonomics
CLASS_SUMMARY_REGISTRY: dict[type[BaseTool], SummaryFunc] = {}


def register_summary(tool_name: str):
    """Decorator to register a summary function for a tool name.

    Supports plain functions and descriptors (staticmethod/classmethod).
    When applied to a descriptor we register the underlying function but
    return the original descriptor so class bodies remain unchanged.
    """

    def decorator(func: SummaryFunc):
        real = getattr(func, "__func__", func)
        SUMMARY_REGISTRY[tool_name] = real
        return func

    return decorator


def register_summaries(*tool_names: str):
    """Decorator to register the same function under multiple tool names."""

    def decorator(func: SummaryFunc):
        real = getattr(func, "__func__", func)
        for name in tool_names:
            SUMMARY_REGISTRY[name] = real
        return func

    return decorator


def register_summary_for(*tool_classes: type[BaseTool]):
    """Decorator to register a summary function for one or more tool classes.

    Also registers the same function under the tool's declared name when available
    to keep ToolResultsStorage (which resolves by name) working without coupling
    it to tool classes.
    """

    def decorator(func: SummaryFunc):
        real = getattr(func, "__func__", func)
        for cls in tool_classes:
            CLASS_SUMMARY_REGISTRY[cls] = real
            # Mirror into name registry for runtime lookup without class
            try:
                name = getattr(cls, "name", None) or cls.__name__.lower()
                # Do not override an explicit name registration if present
                if name not in SUMMARY_REGISTRY:
                    SUMMARY_REGISTRY[name] = real
            except Exception:
                pass
        return func

    return decorator


class ToolRegistry(ToolManager):
    """Backwards-compatible registry type. Extends ToolManager API."""

    def list_tools(self) -> Iterable[LCBaseTool]:
        return list(self._tools.values())

    def get_tool(self, name: str):
        return self.get(name)
