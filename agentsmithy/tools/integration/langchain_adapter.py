from __future__ import annotations

from langchain_core.tools import BaseTool as LCBaseTool

from agentsmithy.tools.registry import ToolRegistry


def as_langchain_tools(manager: ToolRegistry) -> list[LCBaseTool]:
    """Return tools from manager as LangChain tools list via public API."""
    return list(manager.list_tools())
