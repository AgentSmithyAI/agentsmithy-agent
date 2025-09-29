from __future__ import annotations

from typing import Any

from agentsmithy_server.utils.logger import agent_logger

from .base_tool import BaseTool, SseCallback


class ToolRegistry:
    """Simple registry for tools with minimal responsibilities.

    - Store tools by name
    - Propagate SSE callback and dialog_id
    - Execute tools with args_schema validation if present
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._sse_callback: SseCallback | None = None

    def set_sse_callback(self, callback: SseCallback | None) -> None:
        self._sse_callback = callback
        for tool in self._tools.values():
            tool.set_sse_callback(callback)

    def set_dialog_id(self, dialog_id: str | None) -> None:
        for tool in self._tools.values():
            tool.set_dialog_id(dialog_id)

    def set_context(self, project: object | None, dialog_id: str | None) -> None:
        """Propagate project and dialog context to all tools that support it.

        Tools that implement a custom `set_context(project, dialog_id)` will
        receive both the project object and dialog id. We also continue to call
        `set_dialog_id` on all tools for backward compatibility.
        """
        # Backward-compatible propagation of dialog id
        self.set_dialog_id(dialog_id)
        # Optional propagation of project+dialog if tool supports it
        for tool in self._tools.values():
            try:
                setter = getattr(tool, "set_context", None)
                if callable(setter):
                    setter(project, dialog_id)
            except Exception:
                # Best-effort propagation; ignore individual tool failures
                continue

    def register(self, tool: BaseTool) -> None:
        # Ensure required attributes are present on the instance for LangChain binding
        def _field_default(field_name: str):
            try:
                model_fields = getattr(tool.__class__, "model_fields", {})
                if isinstance(model_fields, dict):
                    field_info = model_fields.get(field_name)
                    return getattr(field_info, "default", None)
            except Exception:
                return None
            return None

        # Resolve name in order: pydantic default -> class attribute -> instance attr -> fallback
        name_val = _field_default("name")
        if not isinstance(name_val, str) or not name_val:
            name_val = getattr(tool.__class__, "name", None)
        if not isinstance(name_val, str) or not name_val:
            name_val = getattr(tool, "name", None)
        if not isinstance(name_val, str) or not name_val:
            name_val = tool.__class__.__name__.lower()
        try:
            tool.name = name_val
        except Exception:
            pass

        # Resolve description similarly
        desc_val = _field_default("description")
        if not isinstance(desc_val, str) or not desc_val:
            desc_val = getattr(tool.__class__, "description", None)
        if not isinstance(desc_val, str) or not desc_val:
            desc_val = getattr(tool, "description", None)
        if not isinstance(desc_val, str) or not desc_val:
            desc_val = name_val
        try:
            tool.description = desc_val
        except Exception:
            pass

        # Ensure args_schema attribute exists on the instance
        args_schema_val = getattr(tool, "args_schema", None)
        if args_schema_val is None:
            default_schema = _field_default("args_schema")
            if default_schema is not None:
                try:
                    tool.args_schema = default_schema
                except Exception:
                    pass

        self._tools[str(name_val)] = tool
        tool.set_sse_callback(self._sse_callback)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    async def run_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            # Return a structured error so the LLM can react and recover
            return {
                "type": "tool_error",
                "name": name,
                "error": f"Tool not found: {name}",
                "error_type": "NotFound",
            }
        try:
            agent_logger.info("Tool call", tool=name, args=kwargs)
        except Exception:
            pass

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
                "error": str(ve),
                "error_type": type(ve).__name__,
            }

        # Execute tool and wrap any exception as a structured error
        try:
            # Pass arguments via tool_input dict to satisfy BaseTool.arun signature
            return await tool.arun(args)
        except Exception as e:
            try:
                agent_logger.error(
                    "Tool execution failed",
                    tool=name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
            except Exception:
                pass
            return {
                "type": "tool_error",
                "name": name,
                "error": str(e),
                "error_type": type(e).__name__,
            }
