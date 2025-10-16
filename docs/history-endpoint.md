# Dialog History Endpoint

## Endpoint

```
GET /api/dialogs/{dialog_id}/history
```

Returns complete dialog history as SSE event stream (same format as `POST /api/chat` streaming).

### Parameters

- `dialog_id` (path, required) - Dialog identifier

### Response

```json
{
  "dialog_id": "01J...",
  "events": [...]
}
```

## Event Types

Same as SSE protocol. See `docs/sse-protocol.md` for details.

### user

User message:
```json
{"type": "user", "content": "read file.txt"}
```

### chat

Assistant message:
```json
{"type": "chat", "content": "I'll read the file..."}
```

### reasoning

Model thinking:
```json
{
  "type": "reasoning",
  "content": "**Analyzing request**\n\nI need to read the file first. Then analyze its contents...",
  "model_name": "gpt-4o"
}
```

Note: `model_name` may be absent if not captured.

### tool_call

Tool invocation:
```json
{
  "type": "tool_call",
  "id": "call_abc123",
  "name": "read_file",
  "args": {"path": "file.txt"}
}
```

### file_edit

File modification:
```json
{
  "type": "file_edit",
  "file": "/path/to/file.py",
  "diff": "--- a/...\n+++ b/...",
  "checkpoint": "abc123"
}
```

## Response Examples

### Basic

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Hello"},
    {"type": "chat", "content": "Hi!"}
  ]
}
```

### With Reasoning

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Analyze code"},
    {"type": "reasoning", "content": "First, understand architecture..."},
    {"type": "chat", "content": "I'll analyze..."}
  ]
}
```

### With Tool Calls

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Read file.py"},
    {"type": "reasoning", "content": "I should read it first..."},
    {"type": "chat", "content": "I'll read it"},
    {"type": "tool_call", "id": "call_1", "name": "read_file", "args": {"path": "file.py"}},
    {"type": "chat", "content": "File contains..."}
  ]
}
```

## Event Ordering

Events are returned in chronological order (same as they appeared in SSE stream):

1. User message (`type: "user"`)
2. Reasoning (`type: "reasoning"`) - if model had thinking
3. Assistant response (`type: "chat"`)
4. Tool calls (`type: "tool_call"`) - if any
5. Next assistant response after tool execution

## Errors

**404** - Dialog not found:
```json
{"detail": "Dialog xyz not found"}
```

**500** - Internal error:
```json
{"detail": "Error message..."}
```

## Usage

```bash
curl http://localhost:8000/api/dialogs/{dialog_id}/history | jq '.events'
```

## Notes

- Events match SSE protocol format (see `docs/sse-protocol.md`)
- Null fields are excluded from JSON
- Tool results (`ToolMessage` in LangChain) are not included - only tool invocations
- Use this to replay/render chat UI the same way as during streaming
