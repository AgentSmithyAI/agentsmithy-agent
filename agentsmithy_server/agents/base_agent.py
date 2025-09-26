"""Base agent class for all specialized agents."""

import json
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agentsmithy_server.core import LLMProvider
from agentsmithy_server.core.tool_results_storage import ToolResultsStorage
from agentsmithy_server.rag import ContextBuilder
from agentsmithy_server.utils.logger import agent_logger


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        context_builder: ContextBuilder | None = None,
        system_prompt: str | None = None,
    ):
        self.llm_provider = llm_provider
        self.context_builder = context_builder or ContextBuilder()
        self.system_prompt = system_prompt or self.get_default_system_prompt()

    @abstractmethod
    def get_default_system_prompt(self) -> str:
        """Get the default system prompt for this agent."""
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """Get the name of this agent."""
        pass

    async def process(
        self, query: str, context: dict[str, Any] | None = None, stream: bool = False
    ) -> dict[str, Any]:
        """Process a query with optional context."""
        agent_name = self.get_agent_name()
        agent_logger.debug(
            f"{agent_name} processing query", query_length=len(query), streaming=stream
        )

        # Build context
        full_context = await self.context_builder.build_context(query, context)
        agent_logger.debug(
            f"{agent_name} context built",
            has_current_file=bool(full_context.get("current_file")),
            open_files_count=len(full_context.get("open_files", [])),
            relevant_docs_count=len(full_context.get("relevant_documents", [])),
        )

        # Prepare messages
        messages = self._prepare_messages(query, full_context)
        agent_logger.debug(f"{agent_name} prepared {len(messages)} messages")

        # Generate response
        try:
            if stream:
                agent_logger.debug(f"{agent_name} returning streaming response")
                return {
                    "agent": self.get_agent_name(),
                    "response": self.llm_provider.agenerate(messages, stream=True),
                    "context": full_context,
                }
            else:
                agent_logger.debug(f"{agent_name} generating non-streaming response")
                response = await self.llm_provider.agenerate(messages, stream=False)
                agent_logger.info(
                    f"{agent_name} generated response",
                    response_length=len(response) if isinstance(response, str) else 0,
                )
                return {
                    "agent": self.get_agent_name(),
                    "response": response,
                    "context": full_context,
                }
        except Exception as e:
            agent_logger.error(f"{agent_name} failed to generate response", exception=e)
            raise

    def _prepare_messages(
        self,
        query: str,
        context: dict[str, Any],
        load_tool_results: bool | list[str] = False,
    ) -> list[BaseMessage]:
        """Prepare messages for LLM with lazy loading of tool results.

        Args:
            query: User query
            context: Context including dialog history and project
            load_tool_results:
                - False: Don't load any tool results (default)
                - True: Load all tool results
                - list[str]: Load specific tool_call_ids
        """
        messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]

        # Extract project and dialog_id for tool results loading
        project = context.get("project")
        dialog_id = context.get("dialog", {}).get("id")
        tool_results_storage = None
        # Check if project is a Project object (not a dict from context formatting)
        if project and dialog_id and hasattr(project, "dialogs_dir"):
            tool_results_storage = ToolResultsStorage(project, dialog_id)

        # Add dialog history as actual messages (not as context text)
        if context and context.get("dialog") and context["dialog"].get("messages"):
            from langchain_core.messages import AIMessage

            dialog_messages = context["dialog"]["messages"]

            # Add historical messages
            for msg in dialog_messages:
                # If it's already a BaseMessage object, process it
                if hasattr(msg, "content") and hasattr(msg, "type"):
                    # Special handling for ToolMessage
                    if isinstance(msg, ToolMessage):
                        try:
                            # Ensure content is a string before parsing
                            content = msg.content
                            if isinstance(content, str):
                                content_data = json.loads(content)
                            else:
                                # Skip if content is not a string
                                messages.append(msg)
                                continue
                            # Check if this is a new-style message with result_ref
                            if (
                                isinstance(content_data, dict)
                                and "result_ref" in content_data
                            ):
                                # Decide whether to load full result
                                tool_call_id = content_data.get("tool_call_id", "")
                                should_load = load_tool_results is True or (
                                    isinstance(load_tool_results, list)
                                    and tool_call_id in load_tool_results
                                )

                                if should_load and tool_results_storage:
                                    # Load full result synchronously (we're not in async context)
                                    # For now, keep the reference version
                                    # TODO: Make this method async to support full loading
                                    agent_logger.debug(
                                        "Tool result loading requested but not in async context",
                                        tool_call_id=tool_call_id,
                                    )
                                # History contains only references; no inline results expected.
                                # Keep as-is; the model will use get_tool_result if needed.
                                # Otherwise keep the reference-only version
                        except (json.JSONDecodeError, TypeError):
                            # Old-style ToolMessage with full result, keep as is
                            pass

                    messages.append(msg)
                # Otherwise convert from dict (backward compatibility)
                elif isinstance(msg, dict):
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg["content"]))
                    elif msg.get("role") == "assistant":
                        messages.append(AIMessage(content=msg["content"]))

            # Remove dialog from context to avoid duplication
            context = dict(context)
            context.pop("dialog", None)

        # Remove project object from context before formatting
        # (it's only needed for tool results loading, not for LLM)
        if "project" in context:
            context = dict(context)
            context.pop("project", None)

        # Add remaining context if available
        formatted_context = self.context_builder.format_context_for_prompt(context)
        if formatted_context:
            messages.append(SystemMessage(content=f"Context:\n{formatted_context}"))

        # Add current user query
        messages.append(HumanMessage(content=query))

        return messages
