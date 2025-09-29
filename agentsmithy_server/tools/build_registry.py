from __future__ import annotations

from agentsmithy_server.tools.builtin import TOOL_CLASSES

from .registry import ToolRegistry


def build_registry(
    include: set[str] | None = None, exclude: set[str] | None = None
) -> ToolRegistry:
    """Build tool registry via static registration only.

    Why static:
    - Dynamic autodiscovery (pkgutil/importlib over package paths) breaks in
      PyInstaller onefile binaries because packages are inside an archive and
      not visible as filesystem directories. This leads to missing tools.
    - To ensure consistent behavior across dev and binary builds, we register a
      fixed list of known builtin tools explicitly.
    """
    registry = ToolRegistry()

    include = include or set()
    exclude = exclude or set()

    # Register using the explicit list from builtin package
    for tool_cls in TOOL_CLASSES:
        tool_name = getattr(tool_cls, "name", tool_cls.__name__.lower())
        if include and tool_name not in include:
            continue
        if tool_name in exclude:
            continue
        registry.register(tool_cls())

    return registry
