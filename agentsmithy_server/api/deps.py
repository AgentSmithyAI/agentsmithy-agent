from __future__ import annotations

import asyncio

from agentsmithy_server.core.project import Project, get_current_project
from agentsmithy_server.services.chat_service import ChatService

# Global chat service instance
_chat_service: ChatService | None = None


def get_project() -> Project:
    return get_current_project()


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def set_shutdown_event(event: asyncio.Event) -> None:
    """Set shutdown event on the chat service."""
    service = get_chat_service()
    service.set_shutdown_event(event)
