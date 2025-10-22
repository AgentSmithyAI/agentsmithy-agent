from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

SseCallback = Callable[[dict[str, Any]], Awaitable[None]]


class ToolContext(BaseModel):
    dialog_id: str | None = None
    sse_callback: SseCallback | None = None
    workspace_root: Path | None = None
    # Optional attachments; populated by executor where available
    project: Any | None = None
    file_restrictions: Any | None = None
    versioning: Any | None = None
    results_storage: Any | None = None
