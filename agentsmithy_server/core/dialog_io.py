from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentsmithy_server.core.project import Project


@dataclass
class DialogMessage:
    role: str  # "user" | "assistant"
    content: str
    ts: str | None = None  # ISO timestamp


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _messages_path(project: Project, dialog_id: str) -> Path:
    return project.get_dialog_dir(dialog_id) / "messages.jsonl"


def ensure_dialog(project: Project, dialog_id: str) -> None:
    """Ensure dialog directory exists and is registered in index."""
    dialog_dir = project.get_dialog_dir(dialog_id)
    dialog_dir.mkdir(parents=True, exist_ok=True)
    # Ensure an index entry exists
    project.upsert_dialog_meta(dialog_id)


def append_message(project: Project, dialog_id: str, message: DialogMessage) -> None:
    """Append a message to messages.jsonl and update index timestamps."""
    ensure_dialog(project, dialog_id)
    path = _messages_path(project, dialog_id)
    ts = message.ts or _now_iso()
    record = {"role": message.role, "content": message.content, "ts": ts}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Update dialog metadata in index
    project.upsert_dialog_meta(dialog_id, last_message_at=ts)


def read_messages(
    project: Project,
    dialog_id: str,
    limit: int | None = None,
    reverse: bool = False,
) -> list[dict[str, Any]]:
    """Read messages from messages.jsonl; optionally tail last N.

    If limit is provided, returns the last N messages (preserving chronological order).
    """
    path = _messages_path(project, dialog_id)
    if not path.exists():
        return []

    # Efficient tail for reasonably sized files; for very large files this can be optimized later
    lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    if limit is not None and limit < len(lines):
        lines = lines[-limit:]
    records = [json.loads(line) for line in lines if line.strip()]
    if reverse:
        records.reverse()
    return records


def iter_messages(project: Project, dialog_id: str) -> Iterable[dict[str, Any]]:
    """Iterate all messages in chronological order."""
    path = _messages_path(project, dialog_id)
    if not path.exists():
        return []

    def _gen() -> Iterable[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    return _gen()
