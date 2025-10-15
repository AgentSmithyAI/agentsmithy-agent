# Dialog History Endpoint

## Overview

The `GET /api/dialogs/{dialog_id}/history` endpoint returns complete dialog history including:
- 💬 **Messages** - user and assistant messages
- 💭 **Reasoning blocks** - model's thinking process
- 🔧 **Tool calls** - tool invocations with results

## Endpoint

```
GET /api/dialogs/{dialog_id}/history
```

### Parameters

- `dialog_id` (path, required) - Dialog identifier

### Response: `DialogHistoryResponse`

```json
{
  "dialog_id": "01J...",
  "messages": [...],
  "reasoning_blocks": [...],
  "tool_calls": [...],
  "total_messages": 5,
  "total_reasoning": 2,
  "total_tool_calls": 3
}
```

## Response Schema

### HistoryMessage

```json
{
  "type": "human" | "ai" | "system" | "tool",
  "content": "Message text",
  "index": 0,
  "timestamp": "2025-10-15T20:00:00Z",
  "tool_calls": [
    {
      "id": "call_123",
      "name": "read_file",
      "args": {"path": "file.txt"}
    }
  ]
}
```

**Fields:**
- `type` - message type (human/ai/system/tool)
- `content` - message text
- `index` - sequential position in history (0, 1, 2, ...)
- `timestamp` - creation time (optional)
- `tool_calls` - tool invocations for AI messages (optional)

### ReasoningBlock

```json
{
  "id": 1,
  "content": "I need to analyze the file structure first...",
  "message_index": 3,
  "model_name": "gpt-4o",
  "created_at": "2025-10-15T20:00:01Z"
}
```

**Fields:**
- `id` - unique reasoning block ID
- `content` - full reasoning text
- `message_index` - index of related message in history
- `model_name` - model that generated this reasoning
- `created_at` - creation timestamp

### ToolCallInfo

```json
{
  "tool_call_id": "call_123",
  "tool_name": "read_file",
  "args": {},
  "result_preview": "File content: ...",
  "has_full_result": true,
  "timestamp": "2025-10-15T20:00:02Z",
  "message_index": 3
}
```

**Fields:**
- `tool_call_id` - tool call ID
- `tool_name` - tool name
- `args` - arguments (empty in current version, available via separate endpoint)
- `result_preview` - short result preview (≤200 chars)
- `has_full_result` - whether full result is stored
- `timestamp` - execution time
- `message_index` - index of message that triggered the call

## Usage Examples

### cURL

```bash
# Get history for specific dialog
curl http://localhost:8000/api/dialogs/01J4X2K3M4N5P6Q7R8/history

# Pretty print with jq
curl -s http://localhost:8000/api/dialogs/01J4X2K3M4N5P6Q7R8/history | jq
```

### Python

```python
import requests

dialog_id = "01J4X2K3M4N5P6Q7R8"
response = requests.get(f"http://localhost:8000/api/dialogs/{dialog_id}/history")

if response.status_code == 200:
    data = response.json()
    print(f"Dialog has {data['total_messages']} messages")
    print(f"Dialog has {data['total_reasoning']} reasoning blocks")
    print(f"Dialog has {data['total_tool_calls']} tool calls")
    
    # Show messages with reasoning
    for msg in data['messages']:
        print(f"\n[{msg['index']}] {msg['type']}: {msg['content'][:100]}...")
        
        # Find reasoning for this message
        reasoning = [r for r in data['reasoning_blocks'] if r['message_index'] == msg['index']]
        if reasoning:
            print(f"  💭 Thinking: {reasoning[0]['content'][:80]}...")
```

### JavaScript/TypeScript

```typescript
async function getDialogHistory(dialogId: string) {
  const response = await fetch(
    `http://localhost:8000/api/dialogs/${dialogId}/history`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to fetch history: ${response.statusText}`);
  }
  
  const data = await response.json();
  return data;
}

// Usage
const history = await getDialogHistory("01J4X2K3M4N5P6Q7R8");

// Display timeline
for (const msg of history.messages) {
  console.log(`[${msg.index}] ${msg.type}: ${msg.content}`);
  
  // Show reasoning that led to this message
  const reasoning = history.reasoning_blocks.filter(
    r => r.message_index === msg.index
  );
  
  if (reasoning.length > 0) {
    console.log(`  💭 ${reasoning[0].content}`);
  }
  
  // Show tool calls from this message
  const toolCalls = history.tool_calls.filter(
    tc => tc.message_index === msg.index
  );
  
  for (const tc of toolCalls) {
    console.log(`  🔧 ${tc.tool_name}: ${tc.result_preview}`);
  }
}
```

## Response Examples

### Basic Dialog (Messages Only)

```json
{
  "dialog_id": "abc123",
  "messages": [
    {
      "type": "human",
      "content": "Hello, please help me",
      "index": 0,
      "timestamp": null,
      "tool_calls": null
    },
    {
      "type": "ai",
      "content": "Of course! What do you need help with?",
      "index": 1,
      "timestamp": null,
      "tool_calls": null
    }
  ],
  "reasoning_blocks": [],
  "tool_calls": [],
  "total_messages": 2,
  "total_reasoning": 0,
  "total_tool_calls": 0
}
```

### With Reasoning

```json
{
  "dialog_id": "abc123",
  "messages": [
    {
      "type": "human",
      "content": "Analyze this code",
      "index": 0
    },
    {
      "type": "ai",
      "content": "I'll analyze the code structure...",
      "index": 1
    }
  ],
  "reasoning_blocks": [
    {
      "id": 1,
      "content": "First, I need to understand the architecture. Looking at the imports and class structure...",
      "message_index": 1,
      "model_name": "gpt-4o",
      "created_at": "2025-10-15T20:00:01.123Z"
    }
  ],
  "tool_calls": [],
  "total_messages": 2,
  "total_reasoning": 1,
  "total_tool_calls": 0
}
```

### Complete Example (Messages + Reasoning + Tool Calls)

```json
{
  "dialog_id": "abc123",
  "messages": [
    {
      "type": "human",
      "content": "Read and analyze file.py",
      "index": 0
    },
    {
      "type": "ai",
      "content": "I'll read and analyze the file for you.",
      "index": 1,
      "tool_calls": [
        {
          "id": "call_read_123",
          "name": "read_file",
          "args": {"path": "file.py"}
        }
      ]
    },
    {
      "type": "ai",
      "content": "The file contains a Flask application with 3 routes...",
      "index": 2
    }
  ],
  "reasoning_blocks": [
    {
      "id": 1,
      "content": "I should read the file first to understand its contents before analyzing...",
      "message_index": 1,
      "model_name": "gpt-4o",
      "created_at": "2025-10-15T20:00:01Z"
    },
    {
      "id": 2,
      "content": "Now that I've read the file, I can see it's a Flask app. I should analyze the routes and their functions...",
      "message_index": 2,
      "model_name": "gpt-4o",
      "created_at": "2025-10-15T20:00:03Z"
    }
  ],
  "tool_calls": [
    {
      "tool_call_id": "call_read_123",
      "tool_name": "read_file",
      "args": {},
      "result_preview": "Successfully read file.py...",
      "has_full_result": true,
      "timestamp": "2025-10-15T20:00:02Z",
      "message_index": -1
    }
  ],
  "total_messages": 3,
  "total_reasoning": 2,
  "total_tool_calls": 1
}
```

## Error Responses

### 404 Not Found

```json
{
  "detail": "Dialog nonexistent_id not found"
}
```

When dialog_id doesn't exist.

### 500 Internal Server Error

```json
{
  "detail": "Error message..."
}
```

For internal errors (database issues, etc.).

## Use Cases

### 1. Timeline View

Build complete conversation timeline with reasoning and tool calls:

```python
history = get_dialog_history(dialog_id)

# Build timeline
timeline = []
for msg in history.messages:
    # Add reasoning before message
    for r in history.reasoning_blocks:
        if r.message_index == msg.index:
            timeline.append(("reasoning", r))
    
    # Add message
    timeline.append(("message", msg))
    
    # Add tool calls from message
    if msg.tool_calls:
        for tc_ref in msg.tool_calls:
            tc = next((t for t in history.tool_calls if t.tool_call_id == tc_ref['id']), None)
            if tc:
                timeline.append(("tool_call", tc))

# Display
for item_type, item in timeline:
    if item_type == "reasoning":
        print(f"💭 {item.content[:80]}...")
    elif item_type == "message":
        print(f"💬 {item.type}: {item.content[:80]}...")
    elif item_type == "tool_call":
        print(f"🔧 {item.tool_name}: {item.result_preview[:50]}...")
```

### 2. Export to Markdown

```python
history = get_dialog_history(dialog_id)

with open("dialog_export.md", "w") as f:
    f.write(f"# Dialog {dialog_id}\n\n")
    
    for msg in history.messages:
        # Write reasoning
        for r in history.reasoning_blocks:
            if r.message_index == msg.index:
                f.write(f"**💭 Model thinking ({r.model_name}):**\n\n")
                f.write(f"```\n{r.content}\n```\n\n")
        
        # Write message
        f.write(f"**{msg.type}:** {msg.content}\n\n")
        
        # Write tool calls
        if msg.tool_calls:
            for tc_ref in msg.tool_calls:
                tc = next((t for t in history.tool_calls if t.tool_call_id == tc_ref['id']), None)
                if tc:
                    f.write(f"*Tool: {tc.tool_name}* - {tc.result_preview}\n\n")
```

### 3. Debugging Model Decisions

```python
# Find what model was thinking before specific message
history = get_dialog_history(dialog_id)

message_index = 5  # Analyze message #5
msg = history.messages[message_index]

# Get reasoning for this message
reasoning = [r for r in history.reasoning_blocks if r.message_index == message_index]

print(f"Message #{message_index}: {msg.content}")
if reasoning:
    print(f"\nModel was thinking:")
    for r in reasoning:
        print(f"  {r.content}")
```

### 4. Analytics Dashboard

```python
# Get statistics about dialog
history = get_dialog_history(dialog_id)

print(f"Total messages: {history.total_messages}")
print(f"Total reasoning blocks: {history.total_reasoning}")
print(f"Total tool calls: {history.total_tool_calls}")

# Reasoning usage by model
models = {}
for r in history.reasoning_blocks:
    model = r.model_name or "unknown"
    models[model] = models.get(model, 0) + 1

print("\nReasoning by model:")
for model, count in models.items():
    print(f"  {model}: {count} blocks")

# Tool usage
tools = {}
for tc in history.tool_calls:
    tools[tc.tool_name] = tools.get(tc.tool_name, 0) + 1

print("\nTool calls by type:")
for tool, count in tools.items():
    print(f"  {tool}: {count} calls")
```

## Linking Data

### Message Index

All components are linked via `message_index`:

```
messages[0] = User: "read file"
messages[1] = AI: "I'll read it"         ← reasoning[0].message_index = 1
messages[2] = AI: "File contains..."     ← reasoning[1].message_index = 2
```

### Finding Related Data

```python
# Get message #3 with all related data
msg = history.messages[3]

# Find reasoning for this message
reasoning = [r for r in history.reasoning_blocks if r.message_index == 3]

# Find tool calls referenced in this message
if msg.tool_calls:
    for tc_ref in msg.tool_calls:
        full_tc = next(
            (t for t in history.tool_calls if t.tool_call_id == tc_ref['id']),
            None
        )
        if full_tc:
            print(f"Tool: {full_tc.tool_name}")
            print(f"Preview: {full_tc.result_preview}")
```

## Performance

### Response Time
- **Messages**: Fast (direct SQLite query via LangChain)
- **Reasoning**: Fast (indexed query on dialog_id + created_at)
- **Tool Calls**: Fast (metadata only, indexed)

### Optimization
- Reasoning content is compressed (zlib) to save memory
- Tool results return preview only (full results available via separate endpoint: `/api/dialogs/{dialog_id}/tool-results/{tool_call_id}`)
- Indexes on all critical fields

## Implementation Notes

### Tool Call Args

In current version, `args` in `ToolCallInfo` is empty (`{}`), as `list_results()` returns metadata only.

To get full tool call data, use existing endpoint:
```
GET /api/dialogs/{dialog_id}/tool-results/{tool_call_id}
```

### Message Index Linking

Tool calls currently have `message_index = -1` as direct linking is not stored.

Future enhancement: add `message_index` field to `ToolResultORM` and save it in `store_result()`.

### Reasoning Timing

Reasoning blocks have precise creation timestamp (`created_at`), allowing:
- Timeline reconstruction
- Generation speed analysis
- Correlation with specific dialog moments

## Future Enhancements

Possible improvements:

1. **Query Parameters**:
   - `?include_reasoning=false` - exclude reasoning from response
   - `?include_tool_calls=false` - exclude tool calls
   - `?limit=10` - limit number of messages
   - `?from_index=5` - get history from specific index

2. **Tool Call Linking**:
   - Add `message_index` to `ToolResultORM`
   - Save link in `store_result()`
   - More precise tool call to message binding

3. **Full Tool Args**:
   - Optionally return full args for tool calls
   - Parameter `?include_full_args=true`

4. **Pagination**:
   - For very long dialogs
   - `?page=1&per_page=50`

5. **Filtering**:
   - `?message_type=ai` - only AI messages
   - `?with_reasoning=true` - only messages with reasoning
   - `?tool_name=read_file` - specific tool only

## Testing

```bash
# Run endpoint tests
pytest tests/test_history_endpoint.py -v

# Specific test
pytest tests/test_history_endpoint.py::test_get_history_complete -v
```

**7 tests:**
- ✅ test_get_history_for_nonexistent_dialog
- ✅ test_get_history_with_messages_only
- ✅ test_get_history_with_reasoning
- ✅ test_get_history_with_tool_calls
- ✅ test_get_history_complete
- ✅ test_get_history_with_long_result_preview
- ✅ test_get_history_empty_dialog

## Related Endpoints

- `GET /api/dialogs` - list all dialogs
- `POST /api/dialogs` - create new dialog
- `GET /api/dialogs/{dialog_id}/tool-results/{tool_call_id}` - full tool call result
- `POST /api/chat` - send message (creates history)

## Files

- `agentsmithy_server/api/schemas.py` - data schemas
- `agentsmithy_server/api/routes/history.py` - endpoint implementation
- `agentsmithy_server/api/app.py` - router registration
- `tests/test_history_endpoint.py` - tests

