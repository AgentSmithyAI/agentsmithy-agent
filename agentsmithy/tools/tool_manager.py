from __future__ import annotations

import json
from typing import Any

from agentsmithy.utils.logger import agent_logger

from .base_tool import BaseTool, SseCallback


class ToolManager:
    """Registry and lifecycle manager for tools.

    Holds tools by name, exposes a uniform `run_tool` API, and propagates SSE
    callbacks to all registered tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._sse_callback: SseCallback | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback
        for tool in self._tools.values():
            tool.set_sse_callback(callback)

    def set_dialog_id(self, dialog_id: str | None) -> None:
        """Set dialog_id for all registered tools."""
        for tool in self._tools.values():
            tool.set_dialog_id(dialog_id)

    def set_project_root(self, project_root: str | None) -> None:
        """Set project_root for all registered tools."""
        for tool in self._tools.values():
            if hasattr(tool, "set_project_root"):
                tool.set_project_root(project_root)

    def register(self, tool: BaseTool) -> None:
        # Ensure tool has a usable name/description even if pydantic fields are not set as attrs
        tool_name = getattr(tool, "name", None)
        tool_desc = getattr(tool, "description", None)

        if not tool_name or not isinstance(tool_name, str):
            model_fields = getattr(tool.__class__, "model_fields", {})
            field_info = (
                model_fields.get("name") if isinstance(model_fields, dict) else None
            )
            default_name = getattr(field_info, "default", None)
            tool_name = default_name or tool.__class__.__name__.lower()
            try:
                tool.name = tool_name
            except Exception:
                pass

        if not tool_desc or not isinstance(tool_desc, str):
            model_fields = getattr(tool.__class__, "model_fields", {})
            field_info = (
                model_fields.get("description")
                if isinstance(model_fields, dict)
                else None
            )
            default_desc = getattr(field_info, "default", None)
            tool_desc = default_desc or tool_name
            try:
                tool.description = tool_desc
            except Exception:
                pass

        # Ensure args_schema is present as attribute for LC bind_tools
        tool_args_schema = getattr(tool, "args_schema", None)
        if tool_args_schema is None:
            model_fields = getattr(tool.__class__, "model_fields", {})
            field_info = (
                model_fields.get("args_schema")
                if isinstance(model_fields, dict)
                else None
            )
            default_schema = getattr(field_info, "default", None)
            if default_schema is not None:
                try:
                    tool.args_schema = default_schema
                except Exception:
                    pass

        self._tools[str(tool_name)] = tool
        tool.set_sse_callback(self._sse_callback)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name. Returns True if tool was found and removed."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    async def run_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")
        # Concise log: which tool and with what args
        try:
            agent_logger.info("Tool call", tool=name, args=kwargs)
        except Exception:
            agent_logger.info("Tool call", tool=name)

        # Validate/normalize args via args_schema if available
        args = kwargs
        try:
            schema = getattr(tool, "args_schema", None)
            if schema is not None:
                parsed = schema(**kwargs)
                args = parsed.model_dump()
        except Exception as ve:
            return {
                "type": "tool_error",
                "name": name,
                "code": "args_validation",
                "error": str(ve),
                "error_type": type(ve).__name__,
            }

        try:
            # Pass arguments via tool_input dict to satisfy BaseTool.arun signature
            result = await tool.arun(tool_input=args)
        except Exception as e:
            agent_logger.error(
                "Tool execution failed",
                tool=name,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {
                "type": "tool_error",
                "name": name,
                "code": "execution_failed",
                "error": str(e),
                "error_type": type(e).__name__,
            }

        # Diagnostics: result size
        try:
            serialized = json.dumps(result, ensure_ascii=False)
            agent_logger.info(
                "Tool result",
                tool=name,
                size_bytes=len(serialized.encode("utf-8")),
            )
        except Exception:
            pass

        # No finish log to avoid noise

        return result
