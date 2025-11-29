from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict, TypeGuard


class Vendor(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    OTHER = "other"


# --- Type aliases for LangChain content ---
ContentBlock = str | dict[str, Any]
MessageContent = str | list[ContentBlock]


# --- Reasoning content block types (LangChain Responses API format) ---
# These match what langchain-openai actually returns, not langchain-core's
# ReasoningContentBlock which is incomplete.


class SummaryTextItem(TypedDict, total=False):
    """Single summary text item in reasoning block."""

    index: int
    type: Literal["summary_text"]
    text: str


class ReasoningBlock(TypedDict, total=False):
    """Reasoning content block as returned by LangChain for Responses API.

    LangChain-OpenAI returns reasoning in two possible formats:
    1. Legacy: {"type": "reasoning", "reasoning": "..."}
    2. Responses API v1: {"type": "reasoning", "summary": [...]}
    """

    type: Literal["reasoning"]
    reasoning: str  # Legacy format
    text: str  # Alternative legacy format
    summary: list[SummaryTextItem]  # Responses API v1 format
    index: int
    id: str


class TextContentBlock(TypedDict, total=False):
    """Text content block in AIMessageChunk.content list."""

    type: Literal["text"]
    text: str
    index: int


# --- Tool call types ---


class AccumulatedToolCall(TypedDict):
    """Tool call accumulated from streaming chunks."""

    index: int
    id: str
    name: str
    args: str  # JSON string, parsed later


class ToolCallPayload(TypedDict):
    """Parsed tool call ready for execution."""

    name: str
    args: dict[str, Any]
    id: str


# --- Usage types ---


class NormalizedUsage(TypedDict):
    """Normalized token usage across providers."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


# --- Type guards ---


def is_reasoning_block(block: dict[str, Any]) -> TypeGuard[ReasoningBlock]:
    """Type guard to check if a dict is a ReasoningBlock."""
    return block.get("type") == "reasoning"


def is_text_content_block(block: dict[str, Any]) -> TypeGuard[TextContentBlock]:
    """Type guard to check if a dict is a TextContentBlock."""
    return "text" in block
