"""Simplified SSE Protocol: chat, reasoning, tool_call, file_edit, error, done."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, Optional, Union, Literal


class EventType(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    FILE_EDIT = "file_edit"
    ERROR = "error"
    DONE = "done"


@dataclass
class BaseEvent:
    dialog_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for k, v in list(data.items()):
            if isinstance(v, Enum):
                data[k] = v.value
        return {k: v for k, v in data.items() if v is not None}

    def to_sse(self) -> Dict[str, str]:
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
class ToolCallEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileEditEvent(BaseEvent):
    type: Literal[EventType.FILE_EDIT] = EventType.FILE_EDIT
    file: str = ""


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
    def chat(content: str, dialog_id: Optional[str] = None) -> ChatEvent:
        return ChatEvent(content=content, dialog_id=dialog_id)

    @staticmethod
    def reasoning(content: str, dialog_id: Optional[str] = None) -> ReasoningEvent:
        return ReasoningEvent(content=content, dialog_id=dialog_id)

    @staticmethod
    def tool_call(name: str, args: Dict[str, Any], dialog_id: Optional[str] = None) -> ToolCallEvent:
        return ToolCallEvent(name=name, args=args, dialog_id=dialog_id)

    @staticmethod
    def file_edit(file: str, dialog_id: Optional[str] = None) -> FileEditEvent:
        return FileEditEvent(file=file, dialog_id=dialog_id)

    @staticmethod
    def error(message: str, dialog_id: Optional[str] = None) -> ErrorEvent:
        return ErrorEvent(error=message, dialog_id=dialog_id)

    @staticmethod
    def done(dialog_id: Optional[str] = None) -> DoneEvent:
        return DoneEvent(dialog_id=dialog_id)

    @staticmethod
    def from_dict(data: Dict[str, Any], dialog_id: Optional[str] = None) -> BaseEvent:
        et = data.get("type")
        if dialog_id and "dialog_id" not in data:
            data["dialog_id"] = dialog_id
        if et == EventType.CHAT:
            return ChatEvent(**data)
        if et == EventType.REASONING:
            return ReasoningEvent(**data)
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
