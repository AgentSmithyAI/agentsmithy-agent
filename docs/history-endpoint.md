# Dialog History Endpoint

## Endpoint

```
GET /api/dialogs/{dialog_id}/history
```

Returns complete dialog history as chronological event stream (similar to SSE protocol).

### Parameters

- `dialog_id` (path, required) - Dialog identifier

### Response

```json
{
  "dialog_id": "01J...",
  "messages": [...],
  "total_messages": 5,
  "total_reasoning": 2,
  "total_tool_calls": 1
}
```

## Schema

### HistoryMessage (Event)

Messages is an array of events in chronological order. Each event has different fields based on `type`:

**Human/AI message:**
```json
{
  "type": "human" | "ai",
  "content": "..."
}
```

**Reasoning:**
```json
{
  "type": "reasoning",
  "content": "**Providing installation instructions**\n\nI'm thinking about setup steps. First, `pip install -r requirements.txt`...",
  "model_name": "gpt-4o"  // May be absent if null
}
```

**Tool call:**
```json
{
  "type": "tool_call",
  "tool_name": "read_file",
  "args": {"path": "file.txt"}
}
```

### Fields by Type

| Field | human/ai | reasoning | tool_call |
|-------|----------|-----------|-----------|
| `type` | ✓ | ✓ | ✓ |
| `content` | ✓ | ✓ | - |
| `model_name` | - | ✓ (optional) | - |
| `tool_name` | - | - | ✓ |
| `args` | - | - | ✓ |

**Note:** Fields that are `null` are excluded from JSON response.

## Response Examples

### Basic

```json
{
  "dialog_id": "abc",
  "messages": [
    {"type": "human", "content": "Hello"},
    {"type": "ai", "content": "Hi!"}
  ],
  "total_messages": 2,
  "total_reasoning": 0,
  "total_tool_calls": 0
}
```

### With Reasoning

```json
{
  "dialog_id": "abc",
  "messages": [
    {"type": "human", "content": "Analyze code"},
    {"type": "reasoning", "content": "First, I need to understand...", "model_name": "gpt-4o"},
    {"type": "ai", "content": "I'll analyze..."}
  ],
  "total_messages": 3,
  "total_reasoning": 1,
  "total_tool_calls": 0
}
```

### Complete (with tool calls)

```json
{
  "dialog_id": "abc",
  "messages": [
    {"type": "human", "content": "Read file.py"},
    {"type": "reasoning", "content": "I should read the file first..."},
    {"type": "ai", "content": "I'll read it"},
    {"type": "tool_call", "tool_name": "read_file", "args": {"path": "file.py"}},
    {"type": "ai", "content": "File contains..."}
  ],
  "total_messages": 5,
  "total_reasoning": 1,
  "total_tool_calls": 1
}
```

## Event Ordering

Events are ordered chronologically:
1. **Reasoning** appears before related AI message
2. **Tool calls** appear after AI message that triggered them
3. **AI responses** appear after tool execution

Example flow:
```
[0] human: "do task"
[1] reasoning: "I need to..."
[2] ai: "I'll do it"
[3] tool_call: read_file(...)
[4] ai: "Task done"
```

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
curl http://localhost:8000/api/dialogs/{dialog_id}/history | jq
```

## Notes

- Events ordered chronologically (no need for index field)
- Reasoning `content` may be long (100-500+ words) with markdown/newlines
- Tool call args are included (unlike SSE where they're in separate events)
- No separate `tool_calls` array - everything is in `messages` stream
