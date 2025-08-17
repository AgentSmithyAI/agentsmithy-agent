# AgentSmithy SSE Protocol

This document describes the Server-Sent Events (SSE) protocol used by AgentSmithy to communicate between the server and client (editor).

## Overview

AgentSmithy uses SSE to stream responses from AI agents to the client in real-time. The protocol supports both regular text content and structured file operations (diffs) that the client can apply to files.

## Connection

**Endpoint:** `POST /api/chat`

**Headers:**
```http
Content-Type: application/json
Accept: text/event-stream
Cache-Control: no-cache
```

**Request Body:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "refactor this function"
    }
  ],
  "context": {
    "current_file": {
      "path": "src/example.py",
      "language": "python",
      "content": "def old_function():\n    return 'old'",
      "selection": "def old_function():\n    return 'old'"
    },
    "open_files": [
      {
        "path": "src/utils.py",
        "language": "python", 
        "content": "..."
      }
    ]
  },
  "stream": true
}
```

## Event Types

All events are sent in the standard SSE format:

```
data: {"type": "...", ...}

```

### 1. Classification Event

Sent when the agent determines the task type (optional, may be removed in future versions).

```json
{
  "type": "classification",
  "task_type": "refactor"
}
```

### 2. Content Events

Regular text content from the AI agent.

```json
{
  "content": "I'll refactor this function to improve readability..."
}
```

### 3. Diff Events

File modification events containing unified diffs that can be applied to files.

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

**Diff Event Fields:**
- `type`: Always "diff"
- `file`: Relative path to the file to be modified
- `diff`: Unified diff in standard format
- `line_start`: Starting line number (1-indexed)
- `line_end`: Ending line number (1-indexed, inclusive)
- `reason`: Human-readable explanation of the change

### 4. Completion Event

Signals the end of the stream.

```json
{
  "done": true
}
```

### 5. Error Events

Sent when an error occurs during processing.

```json
{
  "error": "Error message describing what went wrong"
}
```

## Client Implementation Guide

### Basic Event Handling

```javascript
const eventSource = new EventSource('/api/chat');

eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  
  if (data.type === 'diff') {
    handleDiffEvent(data);
  } else if (data.content) {
    handleContentEvent(data);
  } else if (data.done) {
    handleCompletion();
  } else if (data.error) {
    handleError(data);
  }
};
```

### Diff Application

When receiving a diff event, the client should:

1. **Parse the unified diff** using a diff parsing library
2. **Validate the target file** exists and matches expected content
3. **Show a preview** to the user (optional)
4. **Apply the diff** to the file content
5. **Update the editor** with the new content

```javascript
function handleDiffEvent(diffEvent) {
  const { file, diff, reason, line_start, line_end } = diffEvent;
  
  // Parse the unified diff
  const patches = parseDiff(diff);
  
  // Get current file content
  const currentContent = getFileContent(file);
  
  // Apply the diff
  const newContent = applyDiff(currentContent, patches);
  
  // Update the editor
  updateFile(file, newContent, { 
    startLine: line_start, 
    endLine: line_end,
    reason: reason 
  });
}
```

## Agent Behavior

### Edit Block Detection

The agent automatically generates diff events when:

1. **User provides code context** (current file or selection)
2. **Query contains modification keywords**: refactor, improve, optimize, fix, debug, change, update, modify, rename, add, remove, rewrite, clean, simplify, enhance, correct, resolve
3. **Both conditions are met**

### Edit Block Format (Internal)

Agents generate structured edit blocks in their responses:

```
```edit
file: src/example.py
action: edit
line_start: 1
line_end: 2
old_content: |
  def old_function():
      return 'old'
new_content: |
  def improved_function():
      """Better function with documentation."""
      return 'improved'
reason: Improved function naming and added documentation
```
```

These blocks are automatically parsed and converted to diff events.

## Error Handling

### Connection Errors

- **Connection lost**: Client should attempt to reconnect
- **Timeout**: Client should close connection and retry
- **Auth errors**: Client should re-authenticate

### Processing Errors

- **Parse errors**: Invalid JSON in event data
- **Diff application errors**: Conflicts or invalid diffs
- **File errors**: File not found or permission issues

### Error Recovery

```javascript
eventSource.onerror = function(event) {
  console.error('SSE error:', event);
  
  // Close connection
  eventSource.close();
  
  // Retry after delay
  setTimeout(() => {
    reconnect();
  }, 1000);
};
```

## Security Considerations

1. **File Path Validation**: Always validate file paths to prevent directory traversal
2. **Content Validation**: Verify diff content before applying
3. **Rate Limiting**: Implement connection and request rate limits
4. **Authentication**: Secure the SSE endpoint appropriately

## Examples

### Complete Refactoring Flow

1. **User Request:**
```json
{
  "messages": [{"role": "user", "content": "refactor this function"}],
  "context": {
    "current_file": {
      "path": "utils.py",
      "selection": "def calc(x, y):\n    return x + y"
    }
  },
  "stream": true
}
```

2. **Server Response Stream:**
```
data: {"content": "I'll refactor this function for better readability:"}

data: {"type": "diff", "file": "utils.py", "diff": "--- a/utils.py\n+++ b/utils.py\n@@ -1,2 +1,4 @@\n-def calc(x, y):\n-    return x + y\n+def calculate_sum(x: int, y: int) -> int:\n+    \"\"\"Calculate the sum of two integers.\"\"\"\n+    return x + y", "line_start": 1, "line_end": 2, "reason": "Added type hints and documentation"}

data: {"content": "The function now has better naming, type hints, and documentation."}

data: {"done": true}
```

3. **Client Actions:**
- Display explanation text
- Show diff preview
- Apply diff to file
- Update editor with changes

## Version History

- **v1.0**: Initial SSE protocol with diff support
- Current implementation supports unified diff format
- Future versions may add support for additional diff formats or binary files 