"""Regression tests for reasoning extraction from LLM streaming chunks.

These tests verify that reasoning content is correctly extracted using
LangChain's content_blocks API which normalizes reasoning across providers.

If LangChain changes the content_blocks behavior, these tests should fail
and alert us to update accordingly.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessageChunk

from agentsmithy.tools.tool_executor import ToolExecutor


def make_chunk(
    content: list[dict[str, Any]] | str | None = None,
    additional_kwargs: dict[str, Any] | None = None,
    response_metadata: dict[str, Any] | None = None,
) -> AIMessageChunk:
    """Create an AIMessageChunk for testing.

    Uses the real LangChain type to ensure compatibility.
    Always includes model_provider for proper content_blocks translation.
    """
    meta = response_metadata or {}
    if "model_provider" not in meta:
        meta["model_provider"] = "openai"

    return AIMessageChunk(
        content=content or "",
        additional_kwargs=additional_kwargs or {},
        response_metadata=meta,
    )


@pytest.fixture
def executor() -> ToolExecutor:
    """Create a ToolExecutor instance for testing."""
    return ToolExecutor(MagicMock(), MagicMock())


class TestLangChainResponsesV1Format:
    """Tests for LangChain responses/v1 format (langchain-openai >= 1.0.0).

    This is the current default format for OpenAI Responses API models like gpt-5.
    Reasoning comes in content as blocks with 'summary' containing text items.
    content_blocks normalizes 'summary' -> 'reasoning'.
    """

    def test_single_summary_item(self, executor: ToolExecutor) -> None:
        """Extract reasoning from single summary item."""
        chunk = make_chunk(
            content=[
                {
                    "type": "reasoning",
                    "summary": [
                        {"index": 0, "type": "summary_text", "text": "Analyzing..."}
                    ],
                    "index": 0,
                }
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Analyzing..."

    def test_multiple_summary_items(self, executor: ToolExecutor) -> None:
        """Extract and concatenate multiple summary items."""
        chunk = make_chunk(
            content=[
                {
                    "type": "reasoning",
                    "summary": [
                        {"index": 0, "type": "summary_text", "text": "First. "},
                        {"index": 1, "type": "summary_text", "text": "Second."},
                    ],
                    "index": 0,
                }
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "First. Second."

    def test_empty_summary_list(self, executor: ToolExecutor) -> None:
        """Handle empty summary list gracefully."""
        chunk = make_chunk(content=[{"type": "reasoning", "summary": [], "index": 0}])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_summary_item_without_text(self, executor: ToolExecutor) -> None:
        """Handle summary items missing text field."""
        chunk = make_chunk(
            content=[
                {
                    "type": "reasoning",
                    "summary": [{"index": 0, "type": "summary_text"}],
                    "index": 0,
                }
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_mixed_content_blocks(self, executor: ToolExecutor) -> None:
        """Extract reasoning when mixed with other content types."""
        chunk = make_chunk(
            content=[
                {"type": "text", "text": "Hello"},
                {
                    "type": "reasoning",
                    "summary": [{"text": "Thinking..."}],
                },
                {"type": "text", "text": "World"},
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Thinking..."


class TestDirectReasoningField:
    """Tests for content blocks with direct 'reasoning' field.

    content_blocks passes through 'reasoning' field as-is.
    """

    def test_reasoning_key_in_content_block(self, executor: ToolExecutor) -> None:
        """Extract from content block with 'reasoning' key."""
        chunk = make_chunk(
            content=[{"type": "reasoning", "reasoning": "Direct reasoning"}]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Direct reasoning"

    def test_multiple_reasoning_blocks_concatenated(
        self, executor: ToolExecutor
    ) -> None:
        """Multiple reasoning blocks should be concatenated."""
        chunk = make_chunk(
            content=[
                {"type": "reasoning", "reasoning": "First block. "},
                {"type": "reasoning", "reasoning": "Second block."},
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "First block. Second block."


class TestOtherProvidersFormat:
    """Tests for other providers (non-OpenAI) that use additional_kwargs.

    Some providers like Ollama, DeepSeek store reasoning in additional_kwargs.
    content_blocks extracts this when no model_provider is set.
    """

    def test_reasoning_content_in_additional_kwargs_no_provider(
        self, executor: ToolExecutor
    ) -> None:
        """Extract reasoning from additional_kwargs when no provider set."""
        chunk = AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "Legacy reasoning"},
            response_metadata={},  # No model_provider
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Legacy reasoning"


class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_none_content(self, executor: ToolExecutor) -> None:
        """Handle None content gracefully."""
        chunk = make_chunk(content=None)
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_string_content(self, executor: ToolExecutor) -> None:
        """Handle string content (non-list) gracefully."""
        chunk = make_chunk(content="Just a string")
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_empty_content_list(self, executor: ToolExecutor) -> None:
        """Handle empty content list."""
        chunk = make_chunk(content=[])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_empty_reasoning_string(self, executor: ToolExecutor) -> None:
        """Empty reasoning string should return None."""
        chunk = make_chunk(content=[{"type": "reasoning", "reasoning": ""}])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_no_reasoning_blocks(self, executor: ToolExecutor) -> None:
        """No reasoning blocks should return None."""
        chunk = make_chunk(content=[{"type": "text", "text": "Hello"}])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None


class TestContentBlocksIntegration:
    """Integration tests verifying content_blocks behavior.

    These tests verify that LangChain's content_blocks API works as expected.
    If LangChain changes behavior, these tests will catch it.
    """

    def test_content_blocks_normalizes_summary_to_reasoning(self) -> None:
        """Verify content_blocks converts summary to reasoning field."""
        chunk = AIMessageChunk(
            content=[
                {
                    "type": "reasoning",
                    "summary": [{"text": "Test"}],
                }
            ],
            response_metadata={"model_provider": "openai"},
        )
        blocks = chunk.content_blocks
        reasoning_blocks = [b for b in blocks if b.get("type") == "reasoning"]
        assert len(reasoning_blocks) == 1
        assert reasoning_blocks[0].get("reasoning") == "Test"

    def test_content_blocks_extracts_from_additional_kwargs_no_provider(self) -> None:
        """Verify content_blocks extracts reasoning_content when no provider set."""
        chunk = AIMessageChunk(
            content="",
            additional_kwargs={"reasoning_content": "From kwargs"},
            response_metadata={},  # No model_provider - uses fallback
        )
        blocks = chunk.content_blocks
        reasoning_blocks = [b for b in blocks if b.get("type") == "reasoning"]
        assert len(reasoning_blocks) == 1
        assert reasoning_blocks[0].get("reasoning") == "From kwargs"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
