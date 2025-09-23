# Project structure and runtime files

This document describes how AgentSmithy treats a project directory (workdir), what hidden files it creates, and how they are used.

## Workdir and hidden state

- The server starts with a required flag: `--workdir /abs/path/to/project`
- The workdir is treated as a project root
- AgentSmithy uses a hidden directory inside the project: `<workdir>/.agentsmithy`

Contents of `.agentsmithy`:
- `project.json` – metadata about the project (written by the inspector)
- `status.json` – runtime status of the server/scan
- `rag/` – RAG data (e.g., `chroma_db/`)

### Dialogs (MVP)

User/assistant conversation logs are stored in a SQLite database.

- `.agentsmithy/dialogs/index.json` — registry of dialogs:
  - `current_dialog_id`: string | null
  - `dialogs`: array of dialog metadata objects:
    - `id`: string
    - `title`: string | null
    - `created_at`: ISO timestamp
    - `updated_at`: ISO timestamp

- `.agentsmithy/dialogs/messages.sqlite` — SQLite database with message history
  - Messages are stored using LangChain's SQLChatMessageHistory
  - Each dialog_id is a separate session in the database

On first startup (or first chat), if no dialogs exist, a default dialog is created and set current.

## `status.json`

Written atomically on startup and updated during scanning.

Example:
```json
{
  "server_pid": 53124,
  "port": 11434,
  "server_started_at": "2025-08-20T17:34:12Z",
  "scan_status": "idle",
  "scan_started_at": null,
  "scan_updated_at": null,
  "scan_pid": null,
  "scan_task_id": null,
  "scan_error": null,
  "scan_progress": null
}
```



Notes:
- On startup AgentSmithy checks if `server_pid` is alive. If yes, it exits with an error to avoid multiple servers per project
- The server will probe for a free port starting from `SERVER_PORT` (or 11434), and write the chosen port here
- The inspector will update `scan_*` fields during scanning

## `project.json`

Written by the project inspector after a successful scan. Contains a stable `analysis` object used by the agent in prompts.

Example (truncated):
```json
{
  "name": "my-project",
  "root": "/abs/path/my-project",
  "analysis": {
    "language": "Python",
    "frameworks": ["FastAPI"],
    "package_managers": ["pip"],
    "build_tools": [],
    "architecture_hints": ["src", "api"]
  }
}
```

## Singleton behavior and port selection

- Only one server per project is allowed
- On startup:
  - If `status.json` exists and its `server_pid` is alive, the process exits with an error
  - Otherwise, the server probes ports to find a free one and updates `status.json`

## RAG storage

- Project-scoped RAG data lives under: `<workdir>/.agentsmithy/rag/chroma_db`
- Each project gets its own isolated vector store
