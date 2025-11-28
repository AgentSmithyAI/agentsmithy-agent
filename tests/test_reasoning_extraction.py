"""Regression tests for reasoning extraction from LLM streaming chunks.

These tests verify that reasoning content is correctly extracted from various
formats returned by different LLM providers and LangChain versions.

If LangChain or OpenAI SDK changes the format of reasoning blocks, these tests
should fail and alert us to update the extraction logic.
"""

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from agentsmithy.tools.tool_executor import (
    ReasoningBlock,
    SummaryTextItem,
    ToolExecutor,
    is_reasoning_block,
)


@dataclass
class MockChunk:
    """Mock LangChain AIMessageChunk for testing."""

    content: list[dict[str, Any]] | str | None = None
    additional_kwargs: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    reasoning_content: str | None = None


@pytest.fixture
def executor() -> ToolExecutor:
    """Create a ToolExecutor instance for testing."""
    return ToolExecutor(MagicMock(), MagicMock())


class TestReasoningBlockTypeGuard:
    """Tests for is_reasoning_block TypeGuard function."""

    def test_valid_reasoning_block(self) -> None:
        """TypeGuard should return True for valid reasoning blocks."""
        block: dict[str, Any] = {"type": "reasoning", "text": "test"}
        assert is_reasoning_block(block) is True

    def test_invalid_type(self) -> None:
        """TypeGuard should return False for non-reasoning blocks."""
        block: dict[str, Any] = {"type": "text", "text": "test"}
        assert is_reasoning_block(block) is False

    def test_missing_type(self) -> None:
        """TypeGuard should return False when type is missing."""
        block: dict[str, Any] = {"text": "test"}
        assert is_reasoning_block(block) is False


class TestLangChainResponsesV1Format:
    """Tests for LangChain responses/v1 format (langchain-openai >= 1.0.0).

    This is the current default format for OpenAI Responses API models like gpt-5.
    Reasoning comes in content as blocks with 'summary' containing text items.
    """

    def test_single_summary_item(self, executor: ToolExecutor) -> None:
        """Extract reasoning from single summary item."""
        chunk = MockChunk(
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
        chunk = MockChunk(
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
        chunk = MockChunk(content=[{"type": "reasoning", "summary": [], "index": 0}])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_summary_item_without_text(self, executor: ToolExecutor) -> None:
        """Handle summary items missing text field."""
        chunk = MockChunk(
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
        chunk = MockChunk(
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


class TestLangChainLegacyFormat:
    """Tests for legacy LangChain format (langchain-openai < 1.0.0 or output_version='v0').

    In this format, reasoning is stored in additional_kwargs['reasoning'].
    """

    def test_reasoning_string_in_additional_kwargs(
        self, executor: ToolExecutor
    ) -> None:
        """Extract reasoning from additional_kwargs as string."""
        chunk = MockChunk(additional_kwargs={"reasoning": "Direct reasoning text"})
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Direct reasoning text"

    def test_reasoning_dict_with_summary_string(self, executor: ToolExecutor) -> None:
        """Extract reasoning from dict with summary as string."""
        chunk = MockChunk(additional_kwargs={"reasoning": {"summary": "Summary text"}})
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Summary text"

    def test_reasoning_dict_with_content(self, executor: ToolExecutor) -> None:
        """Extract reasoning from dict with content field."""
        chunk = MockChunk(additional_kwargs={"reasoning": {"content": "Content text"}})
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Content text"

    def test_reasoning_in_response_metadata(self, executor: ToolExecutor) -> None:
        """Extract reasoning from response_metadata."""
        chunk = MockChunk(response_metadata={"reasoning": "Metadata reasoning"})
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Metadata reasoning"


class TestContentBlockLegacyFormat:
    """Tests for content block format with direct reasoning/text fields.

    Some providers return reasoning in content blocks with 'reasoning' or 'text' keys
    instead of the 'summary' list format.
    """

    def test_reasoning_key_in_content_block(self, executor: ToolExecutor) -> None:
        """Extract from content block with 'reasoning' key."""
        chunk = MockChunk(
            content=[{"type": "reasoning", "reasoning": "Direct reasoning"}]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Direct reasoning"

    def test_text_key_in_content_block(self, executor: ToolExecutor) -> None:
        """Extract from content block with 'text' key."""
        chunk = MockChunk(content=[{"type": "reasoning", "text": "Text reasoning"}])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Text reasoning"

    def test_reasoning_key_takes_precedence(self, executor: ToolExecutor) -> None:
        """'reasoning' key should take precedence over 'text'."""
        chunk = MockChunk(
            content=[{"type": "reasoning", "reasoning": "Primary", "text": "Secondary"}]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Primary"


class TestReasoningContentAttribute:
    """Tests for direct reasoning_content attribute (OpenAI o1 style).

    Some LangChain adapters expose reasoning directly as an attribute.
    """

    def test_reasoning_content_attribute(self, executor: ToolExecutor) -> None:
        """Extract from reasoning_content attribute."""
        chunk = MockChunk(reasoning_content="Attribute reasoning")
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Attribute reasoning"

    def test_reasoning_content_takes_precedence(self, executor: ToolExecutor) -> None:
        """reasoning_content attribute should take precedence over other sources."""
        chunk = MockChunk(
            reasoning_content="Attribute",
            additional_kwargs={"reasoning": "Kwargs"},
            content=[{"type": "reasoning", "text": "Content"}],
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "Attribute"


class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_none_content(self, executor: ToolExecutor) -> None:
        """Handle None content gracefully."""
        chunk = MockChunk(content=None)
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_string_content(self, executor: ToolExecutor) -> None:
        """Handle string content (non-list) gracefully."""
        chunk = MockChunk(content="Just a string")
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_empty_content_list(self, executor: ToolExecutor) -> None:
        """Handle empty content list."""
        chunk = MockChunk(content=[])
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_empty_reasoning_string(self, executor: ToolExecutor) -> None:
        """Empty reasoning string should return None."""
        chunk = MockChunk(additional_kwargs={"reasoning": ""})
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_empty_reasoning_content_attribute(self, executor: ToolExecutor) -> None:
        """Empty reasoning_content attribute should return None."""
        chunk = MockChunk(reasoning_content="")
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result is None

    def test_multiple_reasoning_blocks_concatenated(
        self, executor: ToolExecutor
    ) -> None:
        """Multiple reasoning blocks should be concatenated."""
        chunk = MockChunk(
            content=[
                {"type": "reasoning", "text": "First block. "},
                {"type": "reasoning", "text": "Second block."},
            ]
        )
        result = executor._extract_reasoning_from_chunk(chunk)
        assert result == "First block. Second block."


class TestTypeDefinitions:
    """Tests to verify TypedDict definitions match expected structure.

    These tests document the expected structure and will fail if the
    TypedDict definitions become incompatible with actual usage.
    """

    def test_reasoning_block_structure(self) -> None:
        """Verify ReasoningBlock TypedDict accepts expected keys."""
        block: ReasoningBlock = {
            "type": "reasoning",
            "reasoning": "test",
            "text": "test",
            "summary": [{"index": 0, "type": "summary_text", "text": "test"}],
            "index": 0,
            "id": "test_id",
        }
        # All keys should be accessible
        assert block.get("type") == "reasoning"
        assert block.get("reasoning") == "test"
        assert block.get("text") == "test"
        assert block.get("summary") is not None
        assert block.get("index") == 0
        assert block.get("id") == "test_id"

    def test_summary_text_item_structure(self) -> None:
        """Verify SummaryTextItem TypedDict accepts expected keys."""
        item: SummaryTextItem = {
            "index": 0,
            "type": "summary_text",
            "text": "test text",
        }
        assert item.get("index") == 0
        assert item.get("type") == "summary_text"
        assert item.get("text") == "test text"

    def test_minimal_reasoning_block(self) -> None:
        """ReasoningBlock should work with minimal required fields."""
        # total=False means all fields are optional
        block: ReasoningBlock = {"type": "reasoning"}
        assert block.get("type") == "reasoning"
        assert block.get("summary") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
