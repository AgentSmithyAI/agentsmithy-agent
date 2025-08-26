"""Domain event types and factory for chat/SSE protocol.

Extracted to core to decouple API layer from event typing and make
streaming adapters reusable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class EventType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    CHAT_START = "chat_start"
    CHAT_END = "chat_end"
    REASONING_START = "reasoning_start"
    REASONING_END = "reasoning_end"
    TOOL_CALL = "tool_call"
    FILE_EDIT = "file_edit"
    ERROR = "error"
    DONE = "done"


@dataclass
class BaseEvent:
    dialog_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for k, v in list(data.items()):
            if isinstance(v, Enum):
                data[k] = v.value
        return {k: v for k, v in data.items() if v is not None}

    def to_sse(self) -> dict[str, str]:
        return {"data": json.dumps(self.to_dict(), ensure_ascii=False)}


@dataclass
class ChatEvent(BaseEvent):
    type: Literal[EventType.CHAT] = EventType.CHAT
    content: str = ""


@dataclass
class ReasoningEvent(BaseEvent):
    type: Literal[EventType.REASONING] = EventType.REASONING
    content: str = ""


@dataclass
class ChatStartEvent(BaseEvent):
    type: Literal[EventType.CHAT_START] = EventType.CHAT_START


@dataclass
class ChatEndEvent(BaseEvent):
    type: Literal[EventType.CHAT_END] = EventType.CHAT_END


@dataclass
class ReasoningStartEvent(BaseEvent):
    type: Literal[EventType.REASONING_START] = EventType.REASONING_START


@dataclass
class ReasoningEndEvent(BaseEvent):
    type: Literal[EventType.REASONING_END] = EventType.REASONING_END


@dataclass
class ToolCallEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileEditEvent(BaseEvent):
    type: Literal[EventType.FILE_EDIT] = EventType.FILE_EDIT
    file: str = ""
    diff: str | None = None
    checkpoint: str | None = None


@dataclass
class ErrorEvent(BaseEvent):
    type: Literal[EventType.ERROR] = EventType.ERROR
    error: str = ""


@dataclass
class DoneEvent(BaseEvent):
    type: Literal[EventType.DONE] = EventType.DONE
    done: bool = True


class EventFactory:
    @staticmethod
    def chat(content: str, dialog_id: str | None = None) -> ChatEvent:
        return ChatEvent(content=content, dialog_id=dialog_id)

    @staticmethod
    def reasoning(content: str, dialog_id: str | None = None) -> ReasoningEvent:
        return ReasoningEvent(content=content, dialog_id=dialog_id)

    @staticmethod
    def chat_start(dialog_id: str | None = None) -> ChatStartEvent:
        return ChatStartEvent(dialog_id=dialog_id)

    @staticmethod
    def chat_end(dialog_id: str | None = None) -> ChatEndEvent:
        return ChatEndEvent(dialog_id=dialog_id)

    @staticmethod
    def reasoning_start(dialog_id: str | None = None) -> ReasoningStartEvent:
        return ReasoningStartEvent(dialog_id=dialog_id)

    @staticmethod
    def reasoning_end(dialog_id: str | None = None) -> ReasoningEndEvent:
        return ReasoningEndEvent(dialog_id=dialog_id)

    @staticmethod
    def tool_call(
        name: str, args: dict[str, Any], dialog_id: str | None = None
    ) -> ToolCallEvent:
        return ToolCallEvent(name=name, args=args, dialog_id=dialog_id)

    @staticmethod
    def file_edit(
        file: str,
        diff: str | None = None,
        checkpoint: str | None = None,
        dialog_id: str | None = None,
    ) -> FileEditEvent:
        return FileEditEvent(
            file=file, diff=diff, checkpoint=checkpoint, dialog_id=dialog_id
        )

    @staticmethod
    def error(message: str, dialog_id: str | None = None) -> ErrorEvent:
        return ErrorEvent(error=message, dialog_id=dialog_id)

    @staticmethod
    def done(dialog_id: str | None = None) -> DoneEvent:
        return DoneEvent(dialog_id=dialog_id)

    @staticmethod
    def from_dict(data: dict[str, Any], dialog_id: str | None = None) -> BaseEvent:
        et = data.get("type")
        if dialog_id and "dialog_id" not in data:
            data["dialog_id"] = dialog_id
        if et == EventType.CHAT:
            return ChatEvent(**data)
        if et == EventType.REASONING:
            return ReasoningEvent(**data)
        if et == EventType.CHAT_START:
            return ChatStartEvent(**data)
        if et == EventType.CHAT_END:
            return ChatEndEvent(**data)
        if et == EventType.REASONING_START:
            return ReasoningStartEvent(**data)
        if et == EventType.REASONING_END:
            return ReasoningEndEvent(**data)
        if et == EventType.TOOL_CALL:
            return ToolCallEvent(**data)
        if et == EventType.FILE_EDIT:
            return FileEditEvent(**data)
        if et == EventType.ERROR:
            return ErrorEvent(**data)
        if et == EventType.DONE or data.get("done"):
            return DoneEvent(**data)
        if "content" in data:
            return ChatEvent(**data)
        return ChatEvent(content=str(data), dialog_id=dialog_id)
