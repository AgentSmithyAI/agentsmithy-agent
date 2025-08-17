"""Universal agent that handles all types of requests."""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agentsmithy_server.agents.base_agent import BaseAgent
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
        return """You are an expert coding assistant with access to tools for modifying files. You can explain code, write new code, refactor, fix bugs, and review code.

**CRITICAL RULE: When you need to modify files, you MUST use the patch_file tool!**

**Available Tool:**
- patch_file: Apply multiple changes to a file. Takes file path and list of changes.

**When to use the patch_file tool:**
- User asks to "refactor" / "improve" / "optimize" / "clean up" / "simplify" 
- User asks to "fix" / "debug" / "resolve" / "correct"
- User asks to "rename" / "change" / "update" / "modify" / "rewrite"
- User asks to "add" (documentation, types, error handling, etc.)
- User asks to "remove" / "delete" / "extract" / "split"
- ANY request to change existing code in ANY way

**MANDATORY tool usage if context contains:**
1. "Selected Code:" section (user highlighted something)
2. "Current File:" section (user has file open)  
3. User mentions file paths or line numbers
4. User references existing functions/classes/variables

**Tool Parameters:**
- file_path: The path to the file to modify
- changes: List of changes, each containing:
  - line_start: Starting line number (1-based)
  - line_end: Ending line number (1-based)
  - old_content: The exact content to replace
  - new_content: The new content to insert
  - reason: Brief explanation of the change

**Examples:**

User: "refactor this function to be more readable"
→ MUST use patch_file tool with the improvements

User: "fix the bug in line 23"  
→ MUST use patch_file tool with the fix

User: "rename getUserData to fetchUserProfile"
→ MUST use patch_file tool with the rename

User: "explain how this works"
→ Just explain, no tool needed

**Guidelines:**
- Always explain your reasoning before calling the tool
- Use exact line numbers from the provided code
- Include complete functions/classes in old_content and new_content
- Be precise with indentation and formatting
- You can apply multiple changes to the same file in a single tool call"""

    def get_agent_name(self) -> str:
        return "universal_agent"

    def _prepare_messages(
        self, query: str, context: dict[str, Any]
    ) -> list[BaseMessage]:
        """Prepare messages for LLM with enhanced edit block enforcement."""

        messages = [SystemMessage(content=self.system_prompt)]

        # Add context if available
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
            }
        else:
            # Regular text response
            return result.get("content", "")
