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

**When Set**: Right after port selection, before server begins listening

**Fields Present**: `server_pid`, `port`, `server_started_at`, `server_updated_at`

**Client Action**: Wait - server is not ready yet

---

### 2. `ready`
**Description**: Server is listening on port and ready to accept requests.

**When Set**: After server startup completes (port is listening, all initialization done)

**Fields Present**: `server_pid`, `port`, `server_started_at`, `server_updated_at`

**Client Action**: Safe to make requests

---

### 3. `stopping`
**Description**: Server received shutdown signal and is gracefully stopping.

**When Set**: After receiving SIGTERM or SIGINT, before cleanup begins

**Fields Present**: `server_pid`, `port`, `server_started_at`, `server_updated_at`

**Client Action**: Server is shutting down, wait or restart

---

### 4. `stopped`
**Description**: Server shut down normally (graceful shutdown completed).

**When Set**: After successful cleanup completes

**Fields Present**: `server_updated_at` only (all server fields cleared)

**Client Action**: Can start new server instance

---

### 5. `error`
**Description**: Server failed to start due to configuration or initialization error.

**When Set**: Configuration validation or initialization failed

**Fields Present**: `server_updated_at`, `server_error` (server_pid and port cleared)

**Client Action**: **Fix configuration before restart**. Status `error` does not block new server startup, but retrying without fixing the issue is pointless.

---

### 6. `crashed`
**Description**: Server terminated unexpectedly (segfault, kill -9, unhandled exception).

**When Set**: Detected by next server start when previous status was running but PID is dead

**Fields Present**: `server_updated_at`, `server_error` (server_pid and port cleared)

**Client Action**: **Safe to retry immediately**. Unlike `error` state, this is not a configuration issue - could be transient failure, OOM, etc. Automatic restart is reasonable.

## Client Implementation Guide

### Starting Server

When starting a server, poll `status.json` until:
- `server_status` becomes `"ready"` AND `server_pid` is alive → proceed
- `server_status` becomes `"error"` → fix configuration before retrying
- Timeout expires → check logs for issues

### Checking Server Status

Clients should:
1. Read `status.json` to get `server_status` and `server_pid`
2. If status is `starting`/`ready`/`stopping`, verify PID is alive
3. If PID is dead but status indicates running → treat as crashed

### Health Check Endpoint

Use the `/health` endpoint to query server status over HTTP (e.g., `GET http://localhost:8765/health`).

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

Status updates are atomic using:
1. **Lock**: Python threading Lock for in-process atomicity
2. **Temp file + rename**: Atomic file writes to prevent corruption

The `StatusManager` class in `agentsmithy/core/status_manager.py` handles all atomic operations.

## See Also

- [Architecture Overview](./architecture.md)
- [Project Structure](./project-structure.md)
- [Graceful Shutdown](./graceful-shutdown.md)

