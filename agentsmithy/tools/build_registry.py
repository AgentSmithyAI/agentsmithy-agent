from __future__ import annotations

from .registry import ToolRegistry


def build_registry(
    include: set[str] | None = None,
    exclude: set[str] | None = None,
) -> ToolRegistry:
    """Build tool registry from explicit builtin TOOL_CLASSES.

    Importing agentsmithy.tools.builtin ensures all builtin tool modules are imported,
    so any decorators (e.g., register_summary_for) run at import time. We then register the
    statically exported TOOL_CLASSES. This approach is robust for PyInstaller onefile builds.

    Note: set_dialog_title is included by default and removed when title is set.
    """
    registry = ToolRegistry()

    include = include or set()
    exclude = exclude or set()

    from agentsmithy.tools.builtin import TOOL_CLASSES as BUILTIN_TOOL_CLASSES

    # Register tools filtered by include/exclude
    for tool_cls in BUILTIN_TOOL_CLASSES:
        tool_name = getattr(tool_cls, "name", tool_cls.__name__.lower())

        if include and tool_name not in include:
            continue
        if tool_name in exclude:
            continue
        registry.register(tool_cls())

    return registry
