# AgentSmithy SSE Protocol

This document describes the Server-Sent Events (SSE) protocol used by AgentSmithy to stream responses and structured file operations to the client (editor).

## Overview

AgentSmithy streams both plain text content and structured events (diffs, tool results). Each SSE message is a single JSON object.

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
  "stream": true
}
```

## Event Format

All events are sent as standard SSE lines:

```
data: {"type": "...", ...}

```

## Event Types

### 1) Classification

Optional early signal about the detected task type.

```json
{ "type": "classification", "task_type": "refactor" }
```
With dialog id:
```json
{ "type": "classification", "task_type": "refactor", "dialog_id": "01J..." }
```

### 2) Content

Plain assistant text content.

```json
{ "content": "I'll refactor this function to improve readability..." }
```
With dialog id:
```json
{ "content": "...", "dialog_id": "01J..." }
```

### 3) Diff

Structured file modification with unified diff that clients can apply.

```json
{
  "type": "diff",
  "file": "src/example.py",
  "diff": "--- a/src/example.py\n+++ b/src/example.py\n@@ -1,2 +1,4 @@\n-def old_function():\n-    return 'old'\n+def improved_function():\n+    \"\"\"Better function with documentation.\"\"\"\n+    return 'improved'",
  "line_start": 1,
  "line_end": 2,
  "reason": "Improved function naming and added documentation"
}
```
With dialog id:
```json
{ "type": "diff", "file": "src/example.py", "diff": "@@ ...", "line_start": 1, "line_end": 2, "reason": "...", "dialog_id": "01J..." }
```

Fields:

- `type`: Always `diff`
- `file`: Target file path
- `diff`: Unified diff string
- `line_start`: Starting line (1-indexed)
- `line_end`: Ending line (inclusive)
- `reason`: Human-readable reason

### 4) Tool Result

Emitted when a tool finishes execution. The `result` field is the tool's structured JSON output.

```json
{
  "type": "tool_result",
  "name": "read_file",
  "result": {
    "type": "read_file_result",
    "path": "/abs/path/to/file.py",
    "content": "...file content..."
  }
}
``;

Notes:

- Tool outputs are serialized JSON; clients can safely parse `result`.
- Additional tool events may also be queued directly by tools (e.g., `diff`).

### 5) Completion

Signals the end of the stream.

```json
{ "done": true }
```
With dialog id:
```json
{ "done": true, "dialog_id": "01J..." }
```

### 6) Error

Errors encountered during processing.

```json
{ "error": "Error message describing what went wrong" }
```

## Client Handling Skeleton

```javascript
const es = new EventSource('/api/chat');

es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'diff') {
    handleDiff(data);
  } else if (data.type === 'tool_result') {
    handleToolResult(data);
  } else if (data.content) {
    handleContent(data);
  } else if (data.done) {
    handleDone();
  } else if (data.error) {
    handleError(data);
  }
};
```

## Diff Application Guidance

1. Parse unified diff with a library
2. Validate the target file content
3. Optionally show a preview
4. Apply diff and update editor buffer

## Example Stream

```
data: {"content": "I'll refactor this function for better readability:"}

data: {"type": "diff", "file": "utils.py", "diff": "--- a/utils.py\n+++ b/utils.py\n@@ -1,2 +1,4 @@\n-def calc(x, y):\n-    return x + y\n+def calculate_sum(x: int, y: int) -> int:\n+    \"\"\"Calculate the sum of two integers.\"\"\"\n+    return x + y", "line_start": 1, "line_end": 2, "reason": "Add type hints and docs"}

data: {"type": "tool_result", "name": "read_file", "result": {"type": "read_file_result", "path": "/abs/path/utils.py", "content": "..."}}

data: {"done": true}
```

## Security Notes

- Validate file paths and diff content
- Rate limit connections
- Authenticate endpoints appropriately


