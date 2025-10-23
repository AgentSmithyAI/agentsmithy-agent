"""SSE Protocol adapter layer.

This module re-exports event classes defined in `agentsmithy.core.events`
to keep backward compatibility with existing imports.
"""

from agentsmithy.domain.events import (
    BaseEvent,
    ChatEndEvent,
    ChatEvent,
    ChatStartEvent,
    CheckpointCreatedEvent,
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
    UserEvent,
)

__all__ = [
    "EventType",
    "BaseEvent",
    "UserEvent",
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
    "CheckpointCreatedEvent",
    "SearchEvent",
    "ErrorEvent",
    "DoneEvent",
    "EventFactory",
]
