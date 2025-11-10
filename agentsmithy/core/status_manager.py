"""Atomic status management for server and scan operations.

This module provides thread-safe status updates to prevent race conditions
where clients might see a PID/port but the server isn't ready yet.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class ServerStatus(str, Enum):
    """Server status states."""

    STARTING = "starting"  # Server process started, initializing
    READY = "ready"  # Server listening and ready for requests
    STOPPING = "stopping"  # Server shutting down gracefully
    STOPPED = "stopped"  # Server stopped normally
    ERROR = "error"  # Server failed due to config/initialization error
    CRASHED = "crashed"  # Server terminated unexpectedly


class ScanStatus(str, Enum):
    """Project scan status states."""

    IDLE = "idle"  # No scan in progress
    SCANNING = "scanning"  # Project scan in progress
    DONE = "done"  # Scan completed successfully
    ERROR = "error"  # Scan failed with error
    CANCELED = "canceled"  # Scan was canceled


class StatusManager:
    """Thread-safe atomic status management for server and scan operations.

    Prevents race conditions by ensuring all status updates are atomic.
    Clients should check server_status == "ready" before making requests.
    """

    def __init__(self, status_path: Path):
        """Initialize status manager.

        Args:
            status_path: Path to status.json file
        """
        self.path = status_path
        self._lock = Lock()

    def _read(self) -> dict[str, Any]:
        """Read current status document."""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, doc: dict[str, Any]) -> None:
        """Atomically write status document using temp file + rename."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
        except Exception:
            # Best-effort; avoid raising at this layer
            pass

    def update_server_status(
        self,
        status: ServerStatus | str,
        *,
        pid: int | None = None,
        port: int | None = None,
        error: str | None = None,
    ) -> None:
        """Atomically update server status fields.

        Args:
            status: Server status enum value or string
            pid: Optional server PID (set on starting)
            port: Optional server port (set on starting)
            error: Optional error message for server failures
        """
        # Convert string to enum if needed
        if isinstance(status, str):
            status = ServerStatus(status)

        with self._lock:
            doc = self._read()
            doc["server_status"] = status.value
            doc["server_updated_at"] = datetime.now(UTC).isoformat()

            if status == ServerStatus.STARTING:
                doc["server_started_at"] = doc["server_updated_at"]
                if pid is not None:
                    doc["server_pid"] = pid
                if port is not None:
                    doc["port"] = port
                # Clear error on new start
                doc.pop("server_error", None)
            elif status == ServerStatus.ERROR:
                # Error state: clear PID/port but keep error message
                # This is for config/validation errors - no point retrying without fix
                doc.pop("server_pid", None)
                doc.pop("port", None)
                if error is not None:
                    doc["server_error"] = error
            elif status == ServerStatus.CRASHED:
                # Crashed state: unexpected termination detected
                # Safe to retry - this is not a config error
                doc.pop("server_pid", None)
                doc.pop("port", None)
                if error is not None:
                    doc["server_error"] = error
            elif status == ServerStatus.STOPPED:
                # Normal stop: clear everything including error
                doc.pop("server_pid", None)
                doc.pop("port", None)
                doc.pop("server_started_at", None)
                doc.pop("server_error", None)
            else:
                # For other states (ready, stopping), clear error
                doc.pop("server_error", None)

            self._write(doc)

    def update_scan_status(
        self,
        status: ScanStatus | str,
        *,
        progress: int | None = None,
        error: str | None = None,
        pid: int | None = None,
        task_id: str | None = None,
    ) -> None:
        """Atomically update scan status fields.

        Args:
            status: Scan status enum value or string
            progress: Optional progress 0-100
            error: Optional error message
            pid: Optional scan process PID
            task_id: Optional scan task identifier
        """
        # Convert string to enum if needed
        if isinstance(status, str):
            status = ScanStatus(status)

        with self._lock:
            doc = self._read()
            now = datetime.now(UTC).isoformat()

            doc["scan_status"] = status.value
            doc["scan_updated_at"] = now

            if status == ScanStatus.SCANNING and not doc.get("scan_started_at"):
                doc["scan_started_at"] = now

            if progress is not None:
                doc["scan_progress"] = max(0, min(100, int(progress)))
            if error is not None:
                doc["error"] = error
            else:
                # Clear error on successful status update
                doc.pop("error", None)
            if pid is not None:
                doc["scan_pid"] = pid
            if task_id is not None:
                doc["scan_task_id"] = task_id

            self._write(doc)

    def get_status(self) -> dict[str, Any]:
        """Read current status atomically.

        Returns:
            Status document with all fields
        """
        with self._lock:
            return self._read()
