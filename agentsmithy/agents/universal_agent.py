"""Universal agent that handles all types of requests."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from agentsmithy.agents.base_agent import BaseAgent
from agentsmithy.dialogs.storages.usage import DialogUsageStorage
from agentsmithy.prompts import UNIVERSAL_SYSTEM
from agentsmithy.tools import ToolExecutor
from agentsmithy.tools.build_registry import build_registry
from agentsmithy.utils.logger import agent_logger


class UniversalAgent(BaseAgent):
    """Universal agent that handles all coding tasks."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initialize tool manager with default tools
        self.tool_manager = build_registry()

        # Initialize tool executor
        self.tool_executor = ToolExecutor(self.tool_manager, self.llm_provider)

        self._sse_callback = None

    def set_sse_callback(self, callback):
        """Set SSE callback for streaming updates."""
        self._sse_callback = callback
        self.tool_manager.set_sse_callback(callback)
        self.tool_executor.set_sse_callback(callback)

    def get_default_system_prompt(self) -> str:
        return UNIVERSAL_SYSTEM

    def get_agent_name(self) -> str:
        return "universal_agent"

    def _manage_title_tool(
        self, dialog_title: str | None, project=None, dialog_id=None
    ) -> None:
        """Remove set_dialog_title tool when title is already set.

        The tool is included by default and should be removed when:
        - Title is set (not None and not empty)
        """
        tool_name = "set_dialog_title"
        has_tool = self.tool_manager.has_tool(tool_name)

        # Remove tool if title is already set
        if dialog_title and has_tool:
            self.tool_manager.unregister(tool_name)
            agent_logger.debug(
                "Removed set_dialog_title tool (title already set)", title=dialog_title
            )

    def _prepare_messages(
        self,
        query: str,
        context: dict[str, Any],
        load_tool_results: bool | list[str] = False,
    ) -> list[BaseMessage]:
        """Delegate message preparation to BaseAgent without extra enforcement."""
        return super()._prepare_messages(query, context, load_tool_results)

    async def process(
        self, query: str, context: dict[str, Any] | None = None, stream: bool = False
    ) -> dict[str, Any]:
        """Process query and return response with file operations if needed."""
        # Concise run log: which agent, model, and input context keys
        agent_logger.info(
            "Agent run",
            agent=self.get_agent_name(),
            model=self.llm_provider.get_model_name(),
            stream=stream,
            context_keys=list((context or {}).keys()),
        )

        # Extract dialog_id and project from context
        dialog_id = None
        project = None
        dialog_title = None
        if context and context.get("dialog"):
            dialog_id = context["dialog"].get("id")
            dialog_title = context["dialog"].get("title")
            # Propagate dialog_id early for all tools
            self.tool_manager.set_dialog_id(dialog_id)

        if context and context.get("project"):
            project = context["project"]

        # Conditionally add/remove set_dialog_title tool based on whether title is set
        self._manage_title_tool(dialog_title, project, dialog_id)

        # Set context for tool executor to enable results storage
        if hasattr(self.tool_executor, "set_context"):
            self.tool_executor.set_context(project, dialog_id)

        # Also propagate project+dialog context to tools that need it
        if hasattr(self.tool_manager, "set_context"):
            # Allows tools like get_tool_result to access storage
            self.tool_manager.set_context(project, dialog_id)

        # Build context
        full_context = await self.context_builder.build_context(query, context)

        # Preserve the original project object in the full context
        # as build_context might have serialized it
        if project:
            full_context["project"] = project

        # Prepare messages
        messages = self._prepare_messages(query, full_context)

        # Wrap result in agent response format
        if stream:
            # For streaming, process_with_tools returns async generator directly
            stream_result = self.tool_executor.process_with_tools(messages, stream=True)

            return {
                "agent": self.get_agent_name(),
                "response": stream_result,  # Already an async generator from _process_streaming
                "context": full_context,
            }
        else:
            # For non-streaming, use the async method
            result = await self.tool_executor.process_with_tools_async(messages)
            # Try to persist usage if present in metadata
            try:
                dialog_id = (
                    full_context.get("dialog", {}).get("id")
                    if isinstance(full_context, dict)
                    else None
                )
                project = (
                    full_context.get("project")
                    if isinstance(full_context, dict)
                    else None
                )
                usage = result.get("usage") if isinstance(result, dict) else None
                if project and dialog_id and usage and hasattr(project, "dialogs_dir"):
                    with DialogUsageStorage(project, dialog_id) as storage:
                        storage.upsert(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            model_name=self.llm_provider.get_model_name(),
                        )
            except Exception:
                pass
            return {
                "agent": self.get_agent_name(),
                "response": self._format_response(result),
                "context": full_context,
            }

    def _format_response(self, result: dict[str, Any]) -> Any:
        """Format the response from tool executor."""
        if result["type"] == "tool_response":
            # Return structured response with tool results
            return {
                "explanation": result.get("content", ""),
                "tool_calls": result.get("tool_calls", []),
                "tool_results": result.get("tool_results", []),
                "conversation": result.get(
                    "conversation", []
                ),  # Include full conversation
            }
        else:
            # Regular text response
            return {
                "content": result.get("content", ""),
                "conversation": result.get(
                    "conversation", []
                ),  # Include conversation even for text
            }
