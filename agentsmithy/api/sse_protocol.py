"""SSE Protocol adapter layer.

This module re-exports event classes defined in `agentsmithy.core.events`
to keep backward compatibility with existing imports.
"""

from agentsmithy.domain.events import (
    BaseEvent,
    ChatEndEvent,
    ChatEvent,
    ChatStartEvent,
    DoneEvent,
    ErrorEvent,
    EventFactory,
    EventType,
    FileEditEvent,
    ReasoningEndEvent,
    ReasoningEvent,
    ReasoningStartEvent,
    SearchEvent,
    SummaryEndEvent,
    SummaryStartEvent,
    ToolCallEvent,
)

__all__ = [
    "EventType",
    "BaseEvent",
    "ChatEvent",
    "ReasoningEvent",
    "ChatStartEvent",
    "ChatEndEvent",
    "ReasoningStartEvent",
    "ReasoningEndEvent",
    "SummaryStartEvent",
    "SummaryEndEvent",
    "ToolCallEvent",
    "FileEditEvent",
    "SearchEvent",
    "ErrorEvent",
    "DoneEvent",
    "EventFactory",
]
