from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict, TypeGuard


class Vendor(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    OTHER = "other"


# --- Type aliases for LangChain content ---
MessageContent = str | list[str | dict[str, Any]]


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


class TextContentBlock(TypedDict, total=False):
    """Text content block in AIMessageChunk.content list."""

    type: Literal["text"]
    text: str
    index: int


def is_text_content_block(block: dict[str, Any]) -> TypeGuard[TextContentBlock]:
    """Type guard to check if a dict is a TextContentBlock."""
    return "text" in block
