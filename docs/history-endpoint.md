# Dialog History Endpoint

## Endpoint

```
GET /api/dialogs/{dialog_id}/history
```

Returns dialog history as SSE event stream (same format as `POST /api/chat` streaming) with cursor-based pagination.

### Parameters

- `dialog_id` (path, required) - Dialog identifier
- `limit` (query, optional) - Maximum number of events to return (default: 20)
- `before` (query, optional) - Cursor to return events before this index (for loading previous events)

### Response

```json
{
  "dialog_id": "01J...",
  "events": [...],
  "total_events": 100,
  "has_more": true,
  "first_idx": 80,
  "last_idx": 99
}
```

**Response fields:**
- `dialog_id` - Dialog identifier
- `events` - Array of history events (in chronological order)
- `total_events` - Total number of events in the full history
- `has_more` - `true` if there are more events before the current page (for infinite scroll)
- `first_idx` - Index of the first event in the returned list
- `last_idx` - Index of the last event in the returned list

## Event Types

Same as SSE protocol. See `docs/sse-protocol.md` for details.

### user

User message:
```json
{"type": "user", "content": "read file.txt", "idx": 0}
```

### chat

Assistant message:
```json
{"type": "chat", "content": "I'll read the file...", "idx": 2}
```

### reasoning

Model thinking:
```json
{
  "type": "reasoning",
  "content": "**Analyzing request**\n\nI need to read the file first. Then analyze its contents...",
  "model_name": "gpt-4o",
  "idx": 1
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
  "args": {"path": "file.txt"},
  "idx": 3
}
```

### file_edit

File modification:
```json
{
  "type": "file_edit",
  "file": "/path/to/file.py",
  "diff": "--- a/...\n+++ b/...",
  "checkpoint": "abc123",
  "idx": 4
}
```

**Note:** All events include an `idx` field - the event's position in the complete history.

## Pagination

### Default Behavior (Last 20 Events)

By default, returns the last 20 events:

```bash
GET /api/dialogs/{dialog_id}/history
# or explicitly
GET /api/dialogs/{dialog_id}/history?limit=20
```

Response:
```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Message 1", "idx": 80},
    {"type": "chat", "content": "Response 1", "idx": 81},
    ...
  ],
  "total_events": 100,
  "has_more": true,
  "first_idx": 80,
  "last_idx": 99
}
```

### Loading Previous Events (Scroll Up)

To load previous events, use the `before` cursor with the `first_idx` from the previous response:

```bash
# First request - get last 20 events
GET /api/dialogs/{dialog_id}/history?limit=20
# Returns: first_idx=80, last_idx=99, has_more=true

# Second request - load 20 more events before index 80
GET /api/dialogs/{dialog_id}/history?limit=20&before=80
# Returns: first_idx=60, last_idx=79, has_more=true

# Third request - continue loading
GET /api/dialogs/{dialog_id}/history?limit=20&before=60
# Returns: first_idx=40, last_idx=59, has_more=true
```

### Custom Page Size

```bash
GET /api/dialogs/{dialog_id}/history?limit=10
```

## Response Examples

### Basic

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Hello", "idx": 0},
    {"type": "chat", "content": "Hi!", "idx": 1}
  ],
  "total_events": 2,
  "has_more": false,
  "first_idx": 0,
  "last_idx": 1
}
```

### With Reasoning

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Analyze code", "idx": 0},
    {"type": "reasoning", "content": "First, understand architecture...", "idx": 1},
    {"type": "chat", "content": "I'll analyze...", "idx": 2}
  ],
  "total_events": 3,
  "has_more": false,
  "first_idx": 0,
  "last_idx": 2
}
```

### With Tool Calls

```json
{
  "dialog_id": "abc",
  "events": [
    {"type": "user", "content": "Read file.py", "idx": 0},
    {"type": "reasoning", "content": "I should read it first...", "idx": 1},
    {"type": "chat", "content": "I'll read it", "idx": 2},
    {"type": "tool_call", "id": "call_1", "name": "read_file", "args": {"path": "file.py"}, "idx": 3},
    {"type": "chat", "content": "File contains...", "idx": 4}
  ],
  "total_events": 5,
  "has_more": false,
  "first_idx": 0,
  "last_idx": 4
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

## Usage Examples

### Get last 20 events

```bash
curl "http://localhost:8000/api/dialogs/{dialog_id}/history" | jq
```

### Get last 10 events

```bash
curl "http://localhost:8000/api/dialogs/{dialog_id}/history?limit=10" | jq
```

### Load previous page (infinite scroll)

```javascript
// Frontend example
async function loadHistory(dialogId, cursor = null) {
  const url = cursor 
    ? `/api/dialogs/${dialogId}/history?limit=20&before=${cursor}`
    : `/api/dialogs/${dialogId}/history?limit=20`;
  
  const response = await fetch(url);
  const data = await response.json();
  
  // data.events - chronologically ordered events
  // data.has_more - true if there are more events to load
  // data.first_idx - use this as cursor for next page
  
  return data;
}

// Load initial (last 20 events)
const page1 = await loadHistory('dialog-id');

// User scrolls up - load previous 20
if (page1.has_more) {
  const page2 = await loadHistory('dialog-id', page1.first_idx);
}
```

## Notes

- **Cursor-based pagination**: Uses `before` cursor (index) to load previous events
- **Chronological order**: Events are always returned in chronological order (oldest first in the array)
- **Default limit**: 20 events per page
- **Event indices**: Each event has an `idx` field with its position in the full history
- Events match SSE protocol format (see `docs/sse-protocol.md`)
- Null fields are excluded from JSON
- Tool results (`ToolMessage` in LangChain) are not included - only tool invocations
- Use this to replay/render chat UI the same way as during streaming
- `has_more: false` means you've reached the beginning of the conversation
