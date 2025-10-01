from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .project import Project


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _status_path(project: Project) -> Path:
    return (project.state_dir / "status.json").resolve()


def read_status(project: Project) -> dict[str, Any]:
    path = _status_path(project)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(project: Project, status_doc: dict[str, Any]) -> None:
    path = _status_path(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(status_doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
    except Exception:
        # Best-effort; avoid raising at this layer
        pass


def set_scan_status(
    project: Project,
    status: str,
    *,
    progress: int | None = None,
    error: str | None = None,
    pid: int | None = None,
    task_id: str | None = None,
) -> None:
    """Update scan-related fields in status.json atomically.

    - status: idle | scanning | done | error | canceled
    - progress: optional 0..100
    - error: optional error message
    - pid/task_id: optional identifiers for the scanning routine
    """
    doc = read_status(project)
    now = datetime.now(UTC).isoformat()
    doc["scan_status"] = status
    if status == "scanning" and not doc.get("scan_started_at"):
        doc["scan_started_at"] = now
    doc["scan_updated_at"] = now
    if progress is not None:
        doc["scan_progress"] = max(0, min(100, int(progress)))
    if error is not None:
        doc["error"] = error
    if pid is not None:
        doc["scan_pid"] = pid
    if task_id is not None:
        doc["scan_task_id"] = task_id
    write_status(project, doc)


def ensure_singleton_and_select_port(
    project: Project,
    base_port: int = 11434,
    host: str = "127.0.0.1",
    max_probe: int = 200,
) -> int:
    """Ensure only one server per project and pick a free port.

    - If existing status has a live server_pid, raise RuntimeError
    - Otherwise pick a free port (starting at base_port), set SERVER_PORT env, and
      write initial status.json with server_pid/port/timestamp, preserving scan fields.
    """
    existing = read_status(project)
    existing_pid = existing.get("server_pid")
    if isinstance(existing_pid, int) and _pid_alive(existing_pid):
        raise RuntimeError(
            f"Server already running for project {project.name} at port {existing.get('port')} (pid {existing_pid})"
        )

    def _port_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return True
            except OSError:
                return False

    chosen = int(os.getenv("SERVER_PORT", str(base_port)))
    for _ in range(max_probe):
        if _port_free(chosen):
            break
        chosen += 1
    else:
        raise RuntimeError(f"Could not find a free port starting at {base_port}")

    # Export to env so settings pick it up
    os.environ["SERVER_PORT"] = str(chosen)

    # Write initial status
    now = datetime.now(UTC).isoformat()
    status_doc: dict[str, Any] = {
        "server_pid": os.getpid(),
        "port": chosen,
        "server_started_at": now,
        "scan_status": existing.get("scan_status") or "idle",
        "scan_started_at": existing.get("scan_started_at"),
        "scan_updated_at": existing.get("scan_updated_at"),
        "scan_pid": existing.get("scan_pid"),
        "scan_task_id": existing.get("scan_task_id"),
        "error": existing.get("error"),
        "scan_progress": existing.get("scan_progress"),
    }
    write_status(project, status_doc)
    return chosen
