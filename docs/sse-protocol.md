# AgentSmithy SSE Protocol

This document describes the simplified Server-Sent Events (SSE) protocol used by AgentSmithy to stream assistant responses and actions to the client.

## Overview

AgentSmithy streams events: `chat_start`, `chat`, `chat_end`, `reasoning_start`, `reasoning`, `reasoning_end`, `tool_call`, `file_edit`, `error`. A final `done` event signals end of stream. Each SSE message is a single JSON object. If an `error` event is emitted, it is immediately followed by a `done` event so clients can reliably finalize the stream.

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

### 1) chat_start

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

### 7) tool_call

Emitted when a tool is invoked by the agent.

```json
{ "type": "tool_call", "name": "read_file", "args": {"path": "src/example.py"}, "dialog_id": "01J..." }
```

### 8) file_edit

Notification that a file was edited/created by a tool. Minimal; clients fetch content separately if needed.

```json
{ "type": "file_edit", "file": "/abs/path/to/file.py", "dialog_id": "01J..." }
```

### 9) error

Errors encountered during processing. Always followed by a `done` event.

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
data: {"type": "reasoning_start", "dialog_id": "01J..."}

data: {"type": "reasoning", "content": "Analyzing functions to update...", "dialog_id": "01J..."}

data: {"type": "reasoning_end", "dialog_id": "01J..."}

data: {"type": "chat_start", "dialog_id": "01J..."}

data: {"type": "chat", "content": "I'll refactor this function for better readability:", "dialog_id": "01J..."}

data: {"type": "chat_end", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "read_file", "args": {"path": "utils.py"}, "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

If an error occurs, the stream will include:

```
data: {"type": "error", "error": "...", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

## Security Notes

- Validate file paths
- Rate limit connections
- Authenticate endpoints appropriately


