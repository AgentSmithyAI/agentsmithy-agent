"""SSE Protocol adapter layer.

This module re-exports event classes defined in `agentsmithy_server.core.events`
to keep backward compatibility with existing imports.
"""

from agentsmithy_server.core.events import (
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
    "ToolCallEvent",
    "FileEditEvent",
    "SearchEvent",
    "ErrorEvent",
    "DoneEvent",
    "EventFactory",
]
