"""Test centralized tool error handling.

Verifies that tool execution errors are handled centrally by tool_manager,
not by tool_executor, and properly propagated to both SSE and model.
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from agentsmithy.domain.events import ErrorEvent
from agentsmithy.tools.base_tool import BaseTool
from agentsmithy.tools.core.types import ToolError
from agentsmithy.tools.registry import ToolRegistry
from agentsmithy.tools.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_tool_execution_error_centralized_handling():
    """Test that tool execution errors are handled by tool_manager and propagated correctly.

    Architecture:
    1. Tool crashes during execution
    2. tool_manager.run_tool() catches exception and returns {"type": "tool_error"}
    3. tool_executor checks result type and handles error
    4. Error is sent to SSE AND added to conversation for model
    """

    # Create a tool that always crashes
    class CrashingTool(BaseTool):
        name: str = "crashing_tool"
        description: str = "A tool that always crashes"

        async def _arun(self, **kwargs):
            raise RuntimeError("Tool crashed during execution!")

    tool_manager = ToolRegistry()
    tool_manager.register(CrashingTool())

    # Mock LLM that yields ONE tool call
    async def mock_llm_stream(messages, **kwargs):
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": "crashing_tool",
                    "args": "{}",  # Valid JSON
                    "id": "call_1",
                    "index": 0,
                }
            ],
        )
        yield chunk

    # Create mock provider
    mock_provider = MagicMock()
    mock_llm = MagicMock()
    mock_provider.bind_tools = MagicMock(return_value=mock_llm)
    mock_provider.bind_tools_without_thinking = MagicMock(return_value=mock_llm)
    mock_llm.astream = MagicMock(side_effect=mock_llm_stream)
    mock_provider.get_stream_kwargs = MagicMock(return_value={})

    executor = ToolExecutor(tool_manager, mock_provider)

    messages = [HumanMessage(content="Test")]

    # Collect chunks
    chunks = []
    error_messages = []

    async for chunk in executor.process_with_tools(messages, stream=True):
        chunks.append(chunk)
        if isinstance(chunk, ErrorEvent):
            error_messages.append(chunk.error)

    # CRITICAL: Only TERMINAL errors should be sent to SSE
    # Tool execution errors are recoverable - should NOT be in SSE individually
    # Only MAX_ITERATIONS error should be sent (terminal)

    assert (
        len(error_messages) > 0
    ), f"Should have at least one terminal error (MAX_ITERATIONS). Chunks: {len(chunks)}"

    # Should be ONLY the terminal error (MAX consecutive errors), not individual tool failures
    terminal_error = error_messages[-1]
    assert (
        "maximum consecutive errors" in terminal_error.lower()
    ), f"Expected MAX consecutive errors (terminal) error. Got: {terminal_error}"

    # Individual tool errors should NOT be in SSE (they are recoverable)
    tool_errors_in_sse = [
        e
        for e in error_messages
        if "crashing_tool" in e.lower() and "maximum" not in e.lower()
    ]
    assert (
        len(tool_errors_in_sse) == 0
    ), f"Recoverable tool errors should NOT be sent to SSE! Found: {tool_errors_in_sse}"

    print("✓ Tool execution errors handled centrally by tool_manager")
    print("✓ Recoverable errors NOT sent to SSE")
    print("✓ Only terminal error (MAX consecutive errors) sent to SSE")
    print(f"✓ Total SSE errors: {len(error_messages)}")


@pytest.mark.asyncio
async def test_tool_manager_catches_all_exceptions():
    """Test that tool_manager.run_tool() catches all exceptions and returns error dict."""

    class ExceptionTool(BaseTool):
        name: str = "exception_tool"
        description: str = "A tool that raises various exceptions"

        async def _arun(self, exception_type: str = "runtime", **kwargs):
            if exception_type == "runtime":
                raise RuntimeError("Runtime error!")
            elif exception_type == "value":
                raise ValueError("Value error!")
            elif exception_type == "type":
                raise TypeError("Type error!")
            elif exception_type == "custom":
                raise Exception("Custom exception!")
            return {"type": "success"}

    tool_manager = ToolRegistry()
    tool_manager.register(ExceptionTool())

    # Test different exception types
    for exc_type in ["runtime", "value", "type", "custom"]:
        result = await tool_manager.run_tool("exception_tool", exception_type=exc_type)

        # tool_manager should catch exception and return ToolError
        assert isinstance(
            result, ToolError
        ), f"Result should be a ToolError for {exc_type}"
        assert result.type == "tool_error", f"Should return tool_error for {exc_type}"
        assert result.error, "ToolError should have 'error' field"
        assert (
            result.code == "execution_failed"
        ), "Error code should be execution_failed"
        assert result.name == "exception_tool", "Error should include tool name"

        print(f"✓ {exc_type} exception caught and converted to ToolError")


@pytest.mark.asyncio
async def test_successful_tool_vs_error_handling():
    """Test that successful tools work normally and only errors trigger error handling."""

    call_count = 0

    class SometimesFailsTool(BaseTool):
        name: str = "sometimes_fails"
        description: str = "A tool that fails on first call, succeeds on second"

        async def _arun(self, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise RuntimeError("First call fails")
            else:
                return {"type": "success", "result": "Second call succeeds"}

    tool_manager = ToolRegistry()
    tool_manager.register(SometimesFailsTool())

    # First call - should fail
    result1 = await tool_manager.run_tool("sometimes_fails")
    assert isinstance(result1, ToolError), "First call should return ToolError"
    assert result1.type == "tool_error", "First call should return tool_error"

    # Second call - should succeed
    result2 = await tool_manager.run_tool("sometimes_fails")
    assert isinstance(result2, dict), "Second call should return dict"
    assert result2.get("type") == "success", "Second call should succeed"
    assert result2.get("result") == "Second call succeeds"

    print("✓ Successful tools work normally")
    print("✓ Failed tools return ToolError")
    print("✓ Tool can recover after failure")
