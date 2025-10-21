from __future__ import annotations

from .registry import ToolRegistry


def build_registry(
    include: set[str] | None = None,
    exclude: set[str] | None = None,
) -> ToolRegistry:
    """Build tool registry from explicit builtin TOOL_CLASSES.

    Importing agentsmithy_server.tools.builtin ensures all builtin tool modules are imported,
    so any decorators (e.g., register_summary_for) run at import time. We then register the
    statically exported TOOL_CLASSES. This approach is robust for PyInstaller onefile builds.

    Note: set_dialog_title is excluded by default and managed dynamically by agents.
    """
    registry = ToolRegistry()

    # Always exclude set_dialog_title - it will be added dynamically when needed
    if exclude is None:
        exclude = {"set_dialog_title"}
    else:
        exclude = set(exclude)
        exclude.add("set_dialog_title")

    include = include or set()

    from agentsmithy_server.tools.builtin import TOOL_CLASSES as BUILTIN_TOOL_CLASSES

    # Register tools filtered by include/exclude
    for tool_cls in BUILTIN_TOOL_CLASSES:
        # Get tool name from model_fields (pydantic) or fallback to class name
        tool_name = None
        if hasattr(tool_cls, "model_fields") and "name" in tool_cls.model_fields:
            tool_name = tool_cls.model_fields["name"].default
        if not tool_name:
            tool_name = tool_cls.__name__.lower()

        if include and tool_name not in include:
            continue
        if tool_name in exclude:
            continue
        registry.register(tool_cls())

    return registry
