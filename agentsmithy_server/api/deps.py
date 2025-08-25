from __future__ import annotations

from functools import lru_cache

from agentsmithy_server.core.project import Project, get_current_project
from agentsmithy_server.services.chat_service import ChatService


def get_project() -> Project:
    return get_current_project()


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    return ChatService()
