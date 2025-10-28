# AgentSmithy SSE Protocol

This document describes the simplified Server-Sent Events (SSE) protocol used by AgentSmithy to stream assistant responses and actions to the client.

## Overview

AgentSmithy streams these event types:

- `user`
- `chat_start`
- `chat`
- `chat_end`
- `reasoning_start`
- `reasoning`
- `reasoning_end`
- `summary_start`
- `summary_end`
- `tool_call`
- `file_edit`
- `error`

A final `done` event signals end of stream. Each SSE message is a single JSON object. If an `error` event is emitted, it is immediately followed by a `done` event so clients can reliably finalize the stream.

## Connection

Endpoint: `POST /api/chat`

Headers:

```http
Content-Type: application/json
Accept: text/event-stream
Cache-Control: no-cache
```

Request Body example:

```json
{
  "messages": [
    { "role": "user", "content": "refactor this function" }
  ],
  "context": {
    "current_file": {
      "path": "src/example.py",
      "language": "python",
      "content": "def old_function():\n    return 'old'",
      "selection": "def old_function():\n    return 'old'"
    }
  },
  "stream": true,
  "dialog_id": "01J..."
}
```

## Event Format

All events are sent as standard SSE lines:

```
data: {"type": "...", ...}

```

## Event Types

### 1) user

User message submitted by the client. Includes checkpoint ID representing the project state BEFORE the AI processes this message.

- `content` (string): The user's message text
- `checkpoint` (string): Git commit ID of checkpoint created before AI processing

```json
{
  "type": "user",
  "content": "Create a TODO app with 3 files",
  "checkpoint": "a1b2c3d4e5f6789abc",
  "dialog_id": "01J..."
}
```

**Purpose:** The checkpoint allows rolling back all changes made by the AI in response to this message.

### 2) chat_start

Marks the beginning of a chat content segment.

```json
{ "type": "chat_start", "dialog_id": "01J..." }
```

### 2) chat

Plain assistant text content.

```json
{ "type": "chat", "content": "I'll refactor this function to improve readability...", "dialog_id": "01J..." }
```

### 3) chat_end

Marks the end of the chat content segment.

```json
{ "type": "chat_end", "dialog_id": "01J..." }
```

### 4) reasoning_start

Marks the beginning of a reasoning segment.

```json
{ "type": "reasoning_start", "dialog_id": "01J..." }
```

### 5) reasoning

Reasoning trace chunks (optional). Use to show model thoughts/steps.

```json
{ "type": "reasoning", "content": "Analyzing functions to update...", "dialog_id": "01J..." }
```

### 6) reasoning_end

Marks the end of the reasoning segment.

```json
{ "type": "reasoning_end", "dialog_id": "01J..." }
```

### 7) summary_start

Marks the beginning of a dialog summarization phase. Emitted even if summarization decides to skip generating a summary (to allow UIs to show a brief spinner).

```json
{ "type": "summary_start", "dialog_id": "01J..." }
```

### 8) summary_end

Marks the end of a dialog summarization phase. Emitted after the system attempts to summarize earlier turns (regardless of whether a summary was produced or a persisted summary was used).

```json
{ "type": "summary_end", "dialog_id": "01J..." }
```

### 9) tool_call

Emitted when a tool is invoked by the agent.

```json
{ "type": "tool_call", "name": "read_file", "args": {"path": "src/example.py"}, "dialog_id": "01J..." }
```

### 10) file_edit

Control signal for the UI to refresh/redraw a file that was modified by a tool.

- `file` (string): absolute path to the edited file
- `diff` (string, optional): unified diff showing changes

```json
{
  "type": "file_edit",
  "file": "/abs/path/to/file.py",
  "diff": "--- a//abs/path/to/file.py\n+++ b//abs/path/to/file.py\n@@ -1,2 +1,2 @@\n line1\n-line2\n+LINE2",
  "dialog_id": "01J..."
}
```

**Purpose:** Notification for UI to refresh the file. The checkpoint for rollback is attached to the `user` event that triggered this change.

### 11) error

Errors encountered during processing. Always followed by a `done` event.

```json
{ "type": "error", "error": "Error message describing what went wrong", "dialog_id": "01J..." }
```

### 12) done

Final event signaling the end of the stream.

```json
{ "type": "done", "done": true, "dialog_id": "01J..." }
```

## Client Handling Skeleton

SSE is streamed over a POST request. Use `fetch` with streaming reader:

```javascript
async function streamChat(body) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(body),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    // keep last partial chunk in buffer
    buffer = chunks.pop() || '';
    for (const chunk of chunks) {
      if (!chunk.startsWith('data: ')) continue;
      const json = JSON.parse(chunk.slice(6));
      handleEvent(json);
    }
  }
}

function handleEvent(data) {
  switch (data.type) {
    case 'chat_start':
      handleChatStart(data);
      break;
    case 'chat':
      handleChat(data);
      break;
    case 'chat_end':
      handleChatEnd(data);
      break;
    case 'reasoning_start':
      handleReasoningStart(data);
      break;
    case 'reasoning':
      handleReasoning(data);
      break;
    case 'reasoning_end':
      handleReasoningEnd(data);
      break;
    case 'tool_call':
      handleToolCall(data);
      break;
    case 'user':
      handleUserMessage(data);
      break;
    case 'file_edit':
      handleFileEdit(data);
      break;
    case 'error':
      handleError(data);
      break;
    case 'done':
      handleDone();
      break;
    default:
      handleChat(data);
  }
}
```

## Web fetching and search

- **Search (`web_search`)**: does not emit a dedicated SSE event; you'll only see the `tool_call` for `web_search`. The actual search results are returned as a tool result and summarized by the model into `chat` chunks.
- **Page fetching (`web_fetch`)**: currently does not emit a dedicated SSE event for payloads. You will see:

  - `tool_call` with `name: "web_fetch"` and the URL args when fetch begins
  - optional `error` if the tool fails
  - any file modifications the tool decides to make as `file_edit`
  - the fetched content is returned in the tool result (added to the model conversation internally) and typically summarized back to the client via `chat` messages

Example sequence for a fetch:

```
data: {"type": "tool_call", "name": "web_fetch", "args": {"url": "https://example.com"}, "dialog_id": "01J..."}

data: {"type": "chat_start", "dialog_id": "01J..."}

data: {"type": "chat", "content": "Fetched https://example.com. The page mentions...", "dialog_id": "01J..."}

data: {"type": "chat_end", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

Note: Large raw page payloads are not streamed as SSE to avoid overwhelming the client; instead, the model is expected to extract and stream relevant summaries via `chat` events. If you need first-class streaming of fetch payloads, consider adding a dedicated event type and emitting it from the `web_fetch` tool.

Example `tool_call` for web search:

```
data: {"type": "tool_call", "name": "web_search", "args": {"query": "fastapi sse", "num_results": 5}, "dialog_id": "01J..."}
```

## Tool result types (non-SSE)

Tools return structured JSON results that are not emitted as SSE events directly. These results are injected back into the model conversation and may lead to `chat`/`file_edit` events.

Common result types include:

- `web_browse_result` / `web_browse_error` — from `web_fetch`
- `web_search_result` / `web_search_error` — from `web_search`
- `read_file_result` / `read_file_error`
- `write_file_result` / `replace_file_result` / `delete_file_result`
- `search_files_result` / `search_files_error`
- `list_files_result` / `list_files_error`
- `run_command_result` / `run_command_error` / `run_command_timeout`
- `tool_error` — generic tool failure wrapper

These appear inside the tool execution pipeline and are summarized to the client via `chat` and `file_edit` where applicable.

## What is streamed vs not

Streamed as SSE (arrive incrementally over the connection):

- `user` (when user submits message; includes checkpoint ID)
- `chat_start`, `chat` (chunks), `chat_end`
- `reasoning_start`, `reasoning` (chunks), `reasoning_end`
- `summary_start`, `summary_end` (bookend summarization phase; no payload chunks yet)
- `tool_call` (when a tool invocation begins; includes tool name and args)
- `file_edit` (when a tool edits/creates/deletes a file; control signal for UI)
- `error` (on failure) followed by `done`
- `done` (always sent to close the stream)

Not streamed (returned as tool results and consumed by the model):

- `web_browse_result` / `web_browse_error` (from `web_fetch`)
- `web_search_result` / `web_search_error` (from `web_search`)
- `read_file_result`, `write_file_result`, `replace_file_result`, `delete_file_result`
- `search_files_result`, `list_files_result`
- `run_command_result`, `run_command_error`, `run_command_timeout`
- `tool_error`

Rationale: heavy payloads (like full HTML) are not streamed as SSE by default to avoid flooding UIs. The model reads tool results and emits concise `chat` updates instead. If your client needs raw payload streaming, introduce a dedicated SSE type and emit it from the tool.

## Example Stream

### Response with file edits

```
data: {"type": "user", "content": "Create a TODO app with 3 files", "checkpoint": "a1b2c3d4e5f6789abc", "dialog_id": "01J..."}

data: {"type": "reasoning_start", "dialog_id": "01J..."}

data: {"type": "reasoning", "content": "Planning TODO app structure...", "dialog_id": "01J..."}

data: {"type": "reasoning_end", "dialog_id": "01J..."}

data: {"type": "chat_start", "dialog_id": "01J..."}

data: {"type": "chat", "content": "I'll create the TODO app with 3 files:", "dialog_id": "01J..."}

data: {"type": "chat_end", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "write_to_file", "args": {"path": "main.py", "content": "..."}, "dialog_id": "01J..."}

data: {"type": "file_edit", "file": "/abs/path/main.py", "diff": "...", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "write_to_file", "args": {"path": "models.py", "content": "..."}, "dialog_id": "01J..."}

data: {"type": "file_edit", "file": "/abs/path/models.py", "diff": "...", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "write_to_file", "args": {"path": "tests.py", "content": "..."}, "dialog_id": "01J..."}

data: {"type": "file_edit", "file": "/abs/path/tests.py", "diff": "...", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

**Note:** The checkpoint `a1b2c3d4e5f6789abc` from the `user` event represents the project state BEFORE the AI created the 3 files. Restoring to this checkpoint will undo all 3 file creations.

If an error occurs, the stream will include:

```
data: {"type": "error", "error": "...", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

## Security Notes

- Validate file paths
- Rate limit connections
- Authenticate endpoints appropriately


