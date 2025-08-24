# AgentSmithy Architecture

This document describes the current server architecture as implemented in the codebase.

## Overview

AgentSmithy is a local AI coding server built with FastAPI. It orchestrates a single Universal Agent that uses tools (function calling) to read/write code and return diffs via SSE.

High level:
- API (FastAPI) exposes `/api/chat` with SSE streaming
- Orchestrator builds a simple graph around one Universal Agent
- Universal Agent formats context, calls the LLM, and executes tools
- Tools perform filesystem operations and can emit structured SSE events (diffs)
- RAG context is per-project and stored under `.agentsmithy/rag/chroma_db`

## Components

### API Layer (`agentsmithy_server/api/server.py`)
- FastAPI app with CORS
- `/api/chat` endpoint for streaming and non‑streaming requests
- Streams content, diff and tool_result events

### Orchestration (`agentsmithy_server/core/agent_graph.py`)
- `AgentOrchestrator` holds the Universal Agent and runs a minimal graph
- Supports streaming state iteration or one‑shot invocation

### LLM Provider (`agentsmithy_server/core/llm_provider.py`)
- `LLMFactory` creates providers; default `OpenAIProvider`
- Provider integrates with `langchain_openai.ChatOpenAI`
- Supports `bind_tools` for native function calling
- Agent model/temperature resolved via pluggable `AgentConfigProvider`

### Universal Agent (`agentsmithy_server/agents/universal_agent.py`)
- Single agent handling all tasks
- Prepares messages (system + formatted context + user)
- Delegates tool execution to `ToolExecutor`
- Returns either text or structured results (diff/tool_results)

### RAG (`agentsmithy_server/rag/*`)
- `ContextBuilder` composes context from current file, open files, and vector store
- `VectorStoreManager` wraps Chroma with project‑scoped persistence

### Project Runtime (`agentsmithy_server/core/project.py`, `project_runtime.py`)
- Project entity owns `state_dir` and RAG paths per project
- Runtime manages singleton server per project and writes `.agentsmithy/status.json`

### Dialogs Persistence (MVP)
- Registry: `<project>/.agentsmithy/dialogs/index.json`
  - `current_dialog_id`, `dialogs[]` (id, title, created/updated/last_message timestamps)
- Messages: `<project>/.agentsmithy/dialogs/<dialog_id>/messages.jsonl` (LDJSON: `{role, content, ts}`)
- On server startup: if no dialogs exist, a default dialog is created and set current

## Request Flow

```mermaid
graph TD
    A[Client Request] --> B[FastAPI /api/chat]
    B --> C[AgentOrchestrator]
    C --> D[UniversalAgent]
    D --> E[ContextBuilder]
    E --> F[LLM Provider (tools bound)]
    F --> G[ToolExecutor]
    G --> H[SSE Streaming]
```

## Structured File Operations

- When code edits are needed the agent returns unified diffs as SSE `type: diff`
- Each diff includes: `file`, `diff`, `line_start`, `line_end`, `reason`

## Streaming (SSE)

- `/api/chat` streams content and structured events
- All SSE events include `dialog_id` when dialog logging is enabled (classification, content chunks, diffs, tool results, completion)

## Configuration

- `.env`: `OPENAI_API_KEY`, `SERVER_HOST`, `SERVER_PORT`, `LOG_FORMAT`
- Agent models resolved via `AgentConfigProvider` (env overrides supported)

## Security/Operational Notes

- Path and diff validation on client side is recommended
- One server per project enforced via `status.json` (port probing + `server_pid`)
