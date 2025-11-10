from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .project import Project
from .status_manager import ScanStatus, ServerStatus, StatusManager


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _status_path(project: Project) -> Path:
    return (project.state_dir / "status.json").resolve()


def get_status_manager(project: Project) -> StatusManager:
    """Get StatusManager instance for a project."""
    return StatusManager(_status_path(project))


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
    status: ScanStatus | str,
    *,
    progress: int | None = None,
    error: str | None = None,
    pid: int | None = None,
    task_id: str | None = None,
) -> None:
    """Update scan-related fields in status.json atomically.

    Args:
        status: Scan status enum value or string
        progress: Optional progress 0-100
        error: Optional error message
        pid: Optional scan process PID
        task_id: Optional scan task identifier
    """
    # Convert string to enum if needed (for backward compatibility)
    if isinstance(status, str):
        status = ScanStatus(status)

    manager = get_status_manager(project)
    manager.update_scan_status(
        status,
        progress=progress,
        error=error,
        pid=pid,
        task_id=task_id,
    )


def set_server_status(
    project: Project,
    status: ServerStatus | str,
    *,
    pid: int | None = None,
    port: int | None = None,
    error: str | None = None,
) -> None:
    """Update server-related fields in status.json atomically.

    Args:
        status: Server status enum value or string
        pid: Optional server PID (set on starting)
        port: Optional server port (set on starting)
        error: Optional error message for server failures
    """
    # Convert string to enum if needed (for backward compatibility)
    if isinstance(status, str):
        status = ServerStatus(status)

    manager = get_status_manager(project)
    manager.update_server_status(status, pid=pid, port=port, error=error)


def ensure_singleton_and_select_port(
    project: Project,
    base_port: int = 8765,
    host: str = "127.0.0.1",
    max_probe: int = 200,
) -> int:
    """Ensure only one server per project and pick a free port.

    - If existing status has a live server_pid with status starting/ready, raise RuntimeError
    - Otherwise pick a free port (starting at base_port), set SERVER_PORT env, and
      write initial status.json with server_status=starting, preserving scan fields.
    """
    existing = read_status(project)
    existing_pid = existing.get("server_pid")
    existing_status = existing.get("server_status")

    # Detect crash: status indicates running but PID is dead
    running_states = {
        ServerStatus.STARTING.value,
        ServerStatus.READY.value,
        ServerStatus.STOPPING.value,
    }
    if (
        isinstance(existing_pid, int)
        and not _pid_alive(existing_pid)
        and existing_status in running_states
    ):
        # Mark as crashed before starting new server
        status_doc = existing.copy()
        status_doc["server_status"] = ServerStatus.CRASHED.value
        status_doc["server_updated_at"] = datetime.now(UTC).isoformat()
        status_doc["server_error"] = (
            f"Server process (pid {existing_pid}) terminated unexpectedly while in '{existing_status}' state"
        )
        status_doc.pop("server_pid", None)
        status_doc.pop("port", None)
        write_status(project, status_doc)

    # Only block if process is alive AND status indicates server is running/starting
    # "error", "crashed", and "stopped" states don't block new server startup
    if (
        isinstance(existing_pid, int)
        and _pid_alive(existing_pid)
        and existing_status in running_states
    ):
        raise RuntimeError(
            f"Server already running for project {project.name} at port {existing.get('port')} (pid {existing_pid}, status {existing_status})"
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

    # Write initial status with server_status="starting"
    # Server is NOT ready yet - still need to initialize dialogs, config, etc.
    now = datetime.now(UTC).isoformat()
    new_status_doc: dict[str, Any] = {
        "server_status": ServerStatus.STARTING.value,
        "server_pid": os.getpid(),
        "port": chosen,
        "server_started_at": now,
        "server_updated_at": now,
        "scan_status": existing.get("scan_status") or ScanStatus.IDLE.value,
        "scan_started_at": existing.get("scan_started_at"),
        "scan_updated_at": existing.get("scan_updated_at"),
        "scan_pid": existing.get("scan_pid"),
        "scan_task_id": existing.get("scan_task_id"),
        "error": existing.get("error"),
        "scan_progress": existing.get("scan_progress"),
    }
    write_status(project, new_status_doc)
    return chosen
