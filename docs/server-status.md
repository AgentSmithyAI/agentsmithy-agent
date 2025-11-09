# Server Status Management

## Overview

AgentSmithy server uses a `status.json` file to track server state and prevent race conditions during startup. This document describes the status lifecycle and how clients should interpret status values.

## Status File Location

The status file is located at:
```
<workdir>/.agentsmithy/status.json
```

## Status Fields

### Server Status Fields

| Field | Type | Description |
|-------|------|-------------|
| `server_status` | string | Current server state: `starting`, `ready`, `stopping`, `stopped`, `error`, `crashed` |
| `server_pid` | integer | Process ID of the running server (cleared on stop/error) |
| `port` | integer | Server port (cleared on stop/error) |
| `server_started_at` | ISO 8601 | Timestamp when server was started |
| `server_updated_at` | ISO 8601 | Timestamp of last status update |
| `server_error` | string | Error message if server failed (only present on `error` state) |

### Scan Status Fields

| Field | Type | Description |
|-------|------|-------------|
| `scan_status` | string | Project scan state: `idle`, `scanning`, `done`, `error`, `canceled` |
| `scan_pid` | integer | Process/task ID performing the scan |
| `scan_task_id` | string | Async task identifier for the scan |
| `scan_progress` | integer | Scan progress 0-100 |
| `scan_started_at` | ISO 8601 | Timestamp when scan started |
| `scan_updated_at` | ISO 8601 | Timestamp of last scan update |
| `error` | string | Error message if scan failed |

## Server Status Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    Server Lifecycle                         │
└─────────────────────────────────────────────────────────────┘

    [Start]
       │
       ├──> Validation Failed ──────────────┐
       │                                     │
       ▼                                     ▼
   starting ────> Initialization Failed ─> error
       │                                     │
       │                                     │ (fix config,
       ▼                                     │  then restart)
  Port Listening                            │
       │                                     │
       ▼                                     │
    ready ◄────────────────────────────────┘
       │
       │
       ├──> Unexpected Crash ───> crashed (next start detects)
       │                             │
       │                             └──> (safe to retry)
       │
       ├──> Received Signal (SIGTERM/SIGINT)
       │
       ▼
   stopping
       │
       ├──> Normal Shutdown ──> stopped
       │
       └──> Crash during shutdown ─> crashed (next start detects)
```

## Status States

### 1. `starting`
**Description**: Server process started, initializing (dialogs, config, etc.) but not yet listening on port.

**When Set**:
- Right after `ensure_singleton_and_select_port()` selects a free port
- Before server begins listening

**Status Fields**:
```json
{
  "server_status": "starting",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:00:00.000Z"
}
```

**Client Action**: Wait - server is not ready yet

---

### 2. `ready`
**Description**: Server is listening on port and ready to accept requests.

**When Set**:
- After `uvicorn.Server.startup()` completes (port is listening)
- All initialization (dialogs, config watcher) completed successfully

**Status Fields**:
```json
{
  "server_status": "ready",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:00:05.123Z"
}
```

**Client Action**: Safe to make requests

---

### 3. `stopping`
**Description**: Server received shutdown signal and is gracefully stopping.

**When Set**:
- After receiving SIGTERM or SIGINT
- Before cleanup begins

**Status Fields**:
```json
{
  "server_status": "stopping",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:05:00.000Z"
}
```

**Client Action**: Server is shutting down, wait or restart

---

### 4. `stopped`
**Description**: Server shut down normally (graceful shutdown completed).

**When Set**:
- After successful cleanup (config watcher stopped, DB closed, etc.)
- All server fields cleared

**Status Fields**:
```json
{
  "server_status": "stopped",
  "server_updated_at": "2025-11-08T12:05:01.000Z",
  "scan_status": "idle"
}
```
Note: `server_pid`, `port`, `server_started_at`, and `server_error` are cleared.

**Client Action**: Can start new server instance

---

### 5. `error`
**Description**: Server failed to start due to configuration or initialization error.

**When Set**:
- Configuration validation failed (missing API keys, invalid settings)
- Initialization failed (dialogs creation, config loading, etc.)

**Status Fields**:
```json
{
  "server_status": "error",
  "server_updated_at": "2025-11-08T12:00:02.000Z",
  "server_error": "Configuration validation failed: OPENAI_API_KEY not set",
  "scan_status": "idle"
}
```
Note: `server_pid` and `port` are cleared when entering error state.

**Client Action**: **Fix configuration before restart**. Status `error` does not block new server startup, but retrying without fixing the issue is pointless.

---

### 6. `crashed`
**Description**: Server terminated unexpectedly (segfault, kill -9, unhandled exception).

**When Set**:
- Detected by next server start: if previous status was `starting`/`ready`/`stopping` but PID is dead
- Automatically marked as `crashed` before new server starts

**Status Fields**:
```json
{
  "server_status": "crashed",
  "server_updated_at": "2025-11-08T12:05:00.000Z",
  "server_error": "Server process (pid 12345) terminated unexpectedly while in 'ready' state",
  "scan_status": "idle"
}
```
Note: `server_pid` and `port` are cleared.

**Client Action**: **Safe to retry immediately**. Unlike `error` state, this is not a configuration issue - could be transient failure, OOM, etc. Automatic restart is reasonable.

## Client Implementation Guide

### Starting Server

```python
def wait_for_server_ready(status_path: Path, timeout: float = 10.0) -> bool:
    """Wait for server to reach 'ready' state.
    
    Returns:
        True if ready, False if error/timeout
    """
    start = time.time()
    
    while time.time() - start < timeout:
        status = read_status_json(status_path)
        server_status = status.get("server_status")
        
        if server_status == "ready":
            # Verify PID is alive
            pid = status.get("server_pid")
            if pid and is_pid_alive(pid):
                return True
        
        elif server_status == "error":
            # Server failed to start
            error = status.get("server_error", "Unknown error")
            raise ServerStartupError(error)
        
        elif server_status in ("stopped", None):
            # Not started or crashed
            continue
        
        time.sleep(0.1)
    
    return False
```

### Checking Server Status

```python
def check_server_status(status_path: Path) -> ServerState:
    """Check current server state."""
    status = read_status_json(status_path)
    server_status = status.get("server_status")
    pid = status.get("server_pid")
    
    # Check for undetected crash (will be marked as crashed on next start)
    if server_status in ("starting", "ready", "stopping"):
        if pid and not is_pid_alive(pid):
            return ServerState.CRASHED
    
    # Map status to state
    status_map = {
        "starting": ServerState.STARTING,
        "ready": ServerState.READY,
        "stopping": ServerState.STOPPING,
        "stopped": ServerState.STOPPED,
        "error": ServerState.ERROR,
        "crashed": ServerState.CRASHED,
    }
    
    return status_map.get(server_status, ServerState.UNKNOWN)
```

### Health Check Endpoint

Clients can also query `/health` endpoint:

```bash
curl http://localhost:8765/health
```

Response:
```json
{
  "status": "ok",
  "service": "agentsmithy-server",
  "server_status": "ready",
  "port": 8765,
  "pid": 12345,
  "server_error": null
}
```

## Singleton Enforcement

Only one server instance per project is allowed:

**Blocking Conditions**:
- `server_pid` is alive AND
- `server_status` is `starting`, `ready`, or `stopping`

**Non-Blocking States**:
- `stopped`: Normal shutdown, safe to start new server
- `error`: Failed startup, safe to restart after fixing config (but pointless to retry without fix)
- `crashed`: Unexpected termination, safe to retry immediately
- No status file: Safe to start
- PID exists but dead: Will be marked as `crashed` before new server starts

## Thread Safety

All status updates are atomic using:
1. **Lock**: Python threading Lock for in-process atomicity
2. **Temp file + rename**: Atomic file writes to prevent corruption

```python
# StatusManager ensures atomic updates
with self._lock:
    doc = self._read()
    doc["server_status"] = "ready"
    self._write(doc)  # Writes to .tmp then renames
```

## Examples

### Example 1: Normal Startup

```json
// Step 1: Starting (port selected but not listening yet)
{
  "server_status": "starting",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:00:00.000Z"
}

// Step 2: Ready (port now listening)
{
  "server_status": "ready",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:00:05.123Z"
}
```

### Example 2: Configuration Error

```json
{
  "server_status": "error",
  "server_updated_at": "2025-11-08T12:00:02.000Z",
  "server_error": "Configuration validation failed: OPENAI_API_KEY not set",
  "scan_status": "idle"
}
```

### Example 3: Crash Detected

```json
// Server crashed while running, detected on next start
{
  "server_status": "crashed",
  "server_updated_at": "2025-11-08T12:10:00.000Z",
  "server_error": "Server process (pid 12345) terminated unexpectedly while in 'ready' state",
  "scan_status": "idle"
}
```

### Example 4: Graceful Shutdown

```json
// Stopping
{
  "server_status": "stopping",
  "server_pid": 12345,
  "port": 8765,
  "server_started_at": "2025-11-08T12:00:00.000Z",
  "server_updated_at": "2025-11-08T12:05:00.000Z"
}

// Stopped
{
  "server_status": "stopped",
  "server_updated_at": "2025-11-08T12:05:01.000Z",
  "scan_status": "idle"
}
```

## See Also

- [Architecture Overview](./architecture.md)
- [Project Structure](./project-structure.md)
- [Graceful Shutdown](./graceful-shutdown.md)

