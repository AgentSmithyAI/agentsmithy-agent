"""Universal agent that handles all types of requests."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agentsmithy_server.agents.base_agent import BaseAgent
from agentsmithy_server.prompts import DEFAULT_SYSTEM_PROMPT
from agentsmithy_server.tools import ToolExecutor, ToolFactory
from agentsmithy_server.utils.logger import agent_logger


class UniversalAgent(BaseAgent):
    """Universal agent that handles all coding tasks."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initialize tool manager with default tools
        self.tool_manager = ToolFactory.create_tool_manager()

        # Initialize tool executor
        self.tool_executor = ToolExecutor(self.tool_manager, self.llm_provider)

        self._sse_callback = None

    def set_sse_callback(self, callback):
        """Set SSE callback for streaming updates."""
        self._sse_callback = callback
        self.tool_manager.set_sse_callback(callback)

    def get_default_system_prompt(self) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_agent_name(self) -> str:
        return "universal_agent"

    def _prepare_messages(
        self, query: str, context: dict[str, Any]
    ) -> list[BaseMessage]:
        """Prepare messages for LLM with enhanced edit block enforcement."""

        messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]

        # Add dialog history as actual messages (not as context text)
        if context and context.get("dialog") and context["dialog"].get("messages"):
            from langchain_core.messages import AIMessage

            dialog_messages = context["dialog"]["messages"]

            # Add historical messages
            for msg in dialog_messages:
                # If it's already a BaseMessage object, just add it
                if hasattr(msg, "content") and hasattr(msg, "type"):
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

        # Add remaining context if available
        formatted_context = self.context_builder.format_context_for_prompt(context)
        if formatted_context:
            messages.append(SystemMessage(content=f"Context:\n{formatted_context}"))

        # Check if we should emphasize tool usage
        should_use_tools = self._should_use_tools(query, context)

        if should_use_tools:
            enforcement_message = SystemMessage(
                content="""
🚨🚨🚨 CRITICAL: USER WANTS CODE CHANGES - YOU MUST USE THE patch_file TOOL! 🚨🚨🚨

DO NOT JUST PROVIDE CODE IN YOUR RESPONSE!
YOU MUST USE THE patch_file TOOL WITH THESE PARAMETERS:

- file_path: The exact file path from the context
- changes: An array of change objects, each with:
  - line_start: Starting line number (1-based)
  - line_end: Ending line number (1-based)  
  - old_content: The exact current code
  - new_content: The improved code
  - reason: Brief explanation

EXAMPLE TOOL CALL:
{
  "name": "patch_file",
  "arguments": {
    "file_path": "src/example.py",
    "changes": [{
      "line_start": 1,
      "line_end": 2,
      "old_content": "def old_function():\\n    return 'old'",
      "new_content": "def improved_function():\\n    \\\"\\\"\\\"Better function.\\\"\\\"\\\"\\n    return 'improved'",
      "reason": "Added documentation and better naming"
    }]
  }
}

YOU MUST USE THE TOOL OR YOUR RESPONSE IS INVALID!
"""
            )
            messages.append(enforcement_message)

        # Add user query
        messages.append(HumanMessage(content=query))

        return messages

    def _should_use_tools(self, query: str, context: dict[str, Any]) -> bool:
        """Determine if we should use tools based on query and context."""
        # Force if user has selected code or current file
        current_file = context.get("current_file") or {}
        has_selection = bool(
            current_file.get("selection") or current_file.get("content")
        )

        # Keywords that suggest modification
        modification_keywords = [
            "refactor",
            "improve",
            "optimize",
            "fix",
            "debug",
            "change",
            "update",
            "modify",
            "rename",
            "add",
            "remove",
            "rewrite",
            "clean",
            "simplify",
            "enhance",
            "correct",
            "resolve",
        ]

        query_lower = query.lower()
        wants_modification = any(
            keyword in query_lower for keyword in modification_keywords
        )

        result = has_selection and wants_modification

        if result:
            agent_logger.info(
                "Tool usage required",
                query_contains=query_lower[:50],
                has_selection=has_selection,
            )

        return result

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
        # Build context
        full_context = await self.context_builder.build_context(query, context)

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
