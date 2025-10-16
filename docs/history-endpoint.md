# Dialog History Endpoint

## Endpoint

```
GET /api/dialogs/{dialog_id}/history
```

Returns complete dialog history including messages (with reasoning inline) and tool calls metadata.

### Parameters

- `dialog_id` (path, required) - Dialog identifier

### Response

```json
{
  "dialog_id": "01J...",
  "messages": [...],
  "tool_calls": [...],
  "total_messages": 5,
  "total_reasoning": 2,
  "total_tool_calls": 1
}
```

## Schema

### HistoryMessage

```json
{
  "type": "human" | "ai" | "reasoning",
  "content": "...",
  "tool_calls": [...] | null,
  "model_name": null
}
```

**Fields:**
- `type` - `human`, `ai`, `system`, `tool`, or `reasoning`
- `content` - message text (can be long-form with markdown/newlines for reasoning)
- `tool_calls` - array for AI messages, `null` for others
- `model_name` - for reasoning messages (may be `null`)

**Reasoning example:**
```json
{
  "type": "reasoning",
  "content": "**Providing installation instructions**\n\nI'm thinking about setup steps. First, I'll mention using `pip install -r requirements.txt` to install dependencies. Then, running the server with `uvicorn agentsmithy_server.api.app:create_app`. Don't forget to configure `.agentsmithy/config.json` including the `providers.openai.api_key` and models.",
  "tool_calls": null,
  "model_name": null
}
```

### ToolCallInfo

```json
{
  "tool_call_id": "call_123",
  "tool_name": "read_file",
  "args": {},
  "result_preview": "...",
  "has_full_result": true,
  "timestamp": "2025-10-15T20:00:02Z",
  "message_index": -1
}
```

**Fields:**
- `tool_call_id` - unique ID
- `tool_name` - tool name
- `args` - empty `{}` (use `/api/dialogs/{dialog_id}/tool-results/{tool_call_id}` for full data)
- `result_preview` - truncated preview (≤200 chars)
- `has_full_result` - whether full result is available
- `timestamp` - execution time
- `message_index` - currently `-1` (not linked)

## Response Examples

### Basic

```json
{
  "dialog_id": "abc",
  "messages": [
    {
      "type": "human",
      "content": "Hello",
      "tool_calls": null,
      "model_name": null
    },
    {
      "type": "ai",
      "content": "Hi there!",
      "tool_calls": null,
      "model_name": null
    }
  ],
  "tool_calls": [],
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
    {
      "type": "human",
      "content": "Analyze code",
      "tool_calls": null,
      "model_name": null
    },
    {
      "type": "reasoning",
      "content": "First, I need to understand the architecture...",
      "tool_calls": null,
      "model_name": "gpt-4o"
    },
    {
      "type": "ai",
      "content": "I'll analyze...",
      "tool_calls": null,
      "model_name": null
    }
  ],
  "tool_calls": [],
  "total_messages": 3,
  "total_reasoning": 1,
  "total_tool_calls": 0
}
```

### Complete

```json
{
  "dialog_id": "abc",
  "messages": [
    {"type": "human", "content": "Read file.py", "tool_calls": null, "model_name": null},
    {"type": "reasoning", "content": "I should read the file first...", "tool_calls": null, "model_name": "gpt-4o"},
    {"type": "ai", "content": "I'll read it", "tool_calls": [{"id": "call_1", "name": "read_file", "args": {"path": "file.py"}}], "model_name": null},
    {"type": "reasoning", "content": "Now analyzing the Flask app...", "tool_calls": null, "model_name": "gpt-4o"},
    {"type": "ai", "content": "The file contains...", "tool_calls": null, "model_name": null}
  ],
  "tool_calls": [
    {
      "tool_call_id": "call_1",
      "tool_name": "read_file",
      "args": {},
      "result_preview": "Successfully read...",
      "has_full_result": true,
      "timestamp": "2025-10-15T20:00:02Z",
      "message_index": -1
    }
  ],
  "total_messages": 5,
  "total_reasoning": 2,
  "total_tool_calls": 1
}
```

## Errors

**404** - Dialog not found:
```json
{"detail": "Dialog nonexistent_id not found"}
```

**500** - Internal error:
```json
{"detail": "Error message..."}
```

## Notes

- Messages are returned in chronological order
- Reasoning messages positioned **before** related AI messages
- Reasoning `content` may be long (100-500+ words) with markdown formatting
- Tool call `args` are empty - use `/api/dialogs/{dialog_id}/tool-results/{tool_call_id}` for full data
