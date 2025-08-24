# AgentSmithy SSE Protocol

This document describes the simplified Server-Sent Events (SSE) protocol used by AgentSmithy to stream assistant responses and actions to the client.

## Overview

AgentSmithy streams five event types: `chat`, `reasoning`, `tool_call`, `file_edit`, `error`. A final `done` event signals end of stream. Each SSE message is a single JSON object.

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

### 1) chat

Plain assistant text content.

```json
{ "type": "chat", "content": "I'll refactor this function to improve readability...", "dialog_id": "01J..." }
```

### 2) reasoning

Reasoning trace chunks (optional). Use to show model thoughts/steps.

```json
{ "type": "reasoning", "content": "Analyzing functions to update...", "dialog_id": "01J..." }
```

### 3) tool_call

Emitted when a tool is invoked by the agent.

```json
{ "type": "tool_call", "name": "read_file", "args": {"path": "src/example.py"}, "dialog_id": "01J..." }
```

### 4) file_edit

Notification that a file was edited/created by a tool. Minimal; clients fetch content separately if needed.

```json
{ "type": "file_edit", "file": "/abs/path/to/file.py", "dialog_id": "01J..." }
```

### 5) error

Errors encountered during processing.

```json
{ "type": "error", "error": "Error message describing what went wrong", "dialog_id": "01J..." }
```

### done

Signals the end of the stream.

```json
{ "type": "done", "done": true, "dialog_id": "01J..." }
```

## Client Handling Skeleton

```javascript
const es = new EventSource('/api/chat');

es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'chat':
      handleChat(data);
      break;
    case 'reasoning':
      handleReasoning(data);
      break;
    case 'tool_call':
      handleToolCall(data);
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
};
```

## Example Stream

```
data: {"type": "chat", "content": "I'll refactor this function for better readability:", "dialog_id": "01J..."}

data: {"type": "reasoning", "content": "Analyzing functions to update...", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "read_file", "args": {"path": "utils.py"}, "dialog_id": "01J..."}

data: {"type": "file_edit", "file": "/abs/path/utils.py", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

## Security Notes

- Validate file paths
- Rate limit connections
- Authenticate endpoints appropriately


