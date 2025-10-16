# Dialog History Endpoint

## Overview

The `GET /api/dialogs/{dialog_id}/history` endpoint returns complete dialog history including:
- 💬 **Messages** - user, assistant, and reasoning messages (inline)
- 🔧 **Tool calls** - tool invocations with results metadata

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
  "messages": [...],  // Includes reasoning inline with type="reasoning"
  "tool_calls": [...],
  "total_messages": 7,      // Total including reasoning messages
  "total_reasoning": 2,     // Count of reasoning messages
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
- `type` - message type: `human`, `ai`, `system`, `tool`, `reasoning`
- `content` - message text
- `index` - sequential position in history (0, 1, 2, ...)
- `timestamp` - creation time (optional)
- `tool_calls` - tool invocations for AI messages (optional)
- `reasoning_id` - unique ID for reasoning messages (optional)
- `model_name` - model name for reasoning messages (optional)

### Reasoning Message (embedded in messages array)

Reasoning is embedded directly in the `messages` array with `type="reasoning"`:

```json
{
  "type": "reasoning",
  "content": "I need to analyze the file structure first...",
  "index": 2,
  "timestamp": "2025-10-15T20:00:01Z",
  "reasoning_id": 1,
  "model_name": "gpt-4o",
  "tool_calls": null
}
```

Reasoning messages are inserted **before** the related AI message in the timeline.

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
    
    # Show all messages (including reasoning inline)
    for msg in data['messages']:
        if msg['type'] == 'reasoning':
            print(f"\n[{msg['index']}] 💭 THINKING ({msg.get('model_name', 'unknown')}):")
            print(f"    {msg['content'][:80]}...")
        else:
            print(f"\n[{msg['index']}] {msg['type']}: {msg['content'][:100]}...")
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
  if (msg.type === 'reasoning') {
    console.log(`[${msg.index}] 💭 ${msg.model_name || 'unknown'}: ${msg.content}`);
  } else {
    console.log(`[${msg.index}] ${msg.type}: ${msg.content}`);
    
    // Show tool calls from this message
    if (msg.tool_calls) {
      for (const tcRef of msg.tool_calls) {
        const tc = history.tool_calls.find(t => t.tool_call_id === tcRef.id);
        if (tc) {
          console.log(`  🔧 ${tc.tool_name}: ${tc.result_preview}`);
        }
      }
    }
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
      "type": "reasoning",
      "content": "First, I need to understand the architecture. Looking at the imports and class structure...",
      "index": 1,
      "timestamp": "2025-10-15T20:00:01.123Z",
      "reasoning_id": 1,
      "model_name": "gpt-4o",
      "tool_calls": null
    },
    {
      "type": "ai",
      "content": "I'll analyze the code structure...",
      "index": 2
    }
  ],
  "tool_calls": [],
  "total_messages": 3,
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
      "type": "reasoning",
      "content": "I should read the file first to understand its contents before analyzing...",
      "index": 1,
      "timestamp": "2025-10-15T20:00:01Z",
      "reasoning_id": 1,
      "model_name": "gpt-4o",
      "tool_calls": null
    },
    {
      "type": "ai",
      "content": "I'll read and analyze the file for you.",
      "index": 2,
      "tool_calls": [
        {
          "id": "call_read_123",
          "name": "read_file",
          "args": {"path": "file.py"}
        }
      ]
    },
    {
      "type": "reasoning",
      "content": "Now that I've read the file, I can see it's a Flask app. I should analyze the routes and their functions...",
      "index": 3,
      "timestamp": "2025-10-15T20:00:03Z",
      "reasoning_id": 2,
      "model_name": "gpt-4o",
      "tool_calls": null
    },
    {
      "type": "ai",
      "content": "The file contains a Flask application with 3 routes...",
      "index": 4
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
  "total_messages": 5,
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

Messages already form a complete timeline with reasoning embedded:

```python
history = get_dialog_history(dialog_id)

# Display timeline (reasoning is already inline)
for msg in history.messages:
    if msg.type == "reasoning":
        print(f"[{msg.index}] 💭 {msg.model_name}: {msg.content[:80]}...")
    elif msg.type in ("human", "ai"):
        print(f"[{msg.index}] 💬 {msg.type}: {msg.content[:80]}...")
        
        # Show tool calls if any
        if msg.tool_calls:
            for tc_ref in msg.tool_calls:
                tc = next((t for t in history.tool_calls if t.tool_call_id == tc_ref['id']), None)
                if tc:
                    print(f"  🔧 {tc.tool_name}: {tc.result_preview[:50]}...")
```

### 2. Export to Markdown

```python
history = get_dialog_history(dialog_id)

with open("dialog_export.md", "w") as f:
    f.write(f"# Dialog {dialog_id}\n\n")
    
    for msg in history.messages:
        if msg.type == "reasoning":
            # Write reasoning
            f.write(f"**💭 Model thinking ({msg.model_name}):**\n\n")
            f.write(f"```\n{msg.content}\n```\n\n")
        else:
            # Write regular message
            f.write(f"**{msg.type}:** {msg.content}\n\n")
            
            # Write tool calls if present
            if msg.tool_calls:
                for tc_ref in msg.tool_calls:
                    tc = next((t for t in history.tool_calls if t.tool_call_id == tc_ref['id']), None)
                    if tc:
                        f.write(f"*Tool: {tc.tool_name}* - {tc.result_preview}\n\n")
```

### 3. Debugging Model Decisions

```python
# Find reasoning that precedes specific message
history = get_dialog_history(dialog_id)

target_index = 5  # Analyze message #5
msg = history.messages[target_index]

# Find reasoning message that came just before (will have lower index)
print(f"Message #{target_index}: {msg.content}")

# Look backwards for reasoning
for i in range(target_index - 1, -1, -1):
    prev_msg = history.messages[i]
    if prev_msg.type == "reasoning":
        print(f"\nModel was thinking:")
        print(f"  {prev_msg.content}")
        break
    elif prev_msg.type in ("human", "ai"):
        # Stop at previous non-reasoning message
        break
```

### 4. Analytics Dashboard

```python
# Get statistics about dialog
history = get_dialog_history(dialog_id)

print(f"Total messages: {history.total_messages}")
print(f"Total reasoning: {history.total_reasoning}")
print(f"Total tool calls: {history.total_tool_calls}")

# Reasoning usage by model
models = {}
for msg in history.messages:
    if msg.type == "reasoning":
        model = msg.model_name or "unknown"
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

## Message Ordering

### Timeline Structure

Reasoning messages are inserted **before** their related AI messages:

```
messages[0] = User: "read file"
messages[1] = Reasoning: "I need to read the file..."  (type="reasoning")
messages[2] = AI: "I'll read it"                      (type="ai")
messages[3] = Reasoning: "Now analyzing..."           (type="reasoning")
messages[4] = AI: "File contains..."                  (type="ai")
```

### Finding Related Data

```python
# Get message #3 with all related data
msg = history.messages[3]

if msg.type == "ai":
    # Look backwards for preceding reasoning
    for i in range(msg.index - 1, -1, -1):
        prev = history.messages[i]
        if prev.type == "reasoning":
            print(f"Model was thinking: {prev.content}")
            break
        elif prev.type in ("human", "ai"):
            break

# Find tool calls referenced in AI message
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

