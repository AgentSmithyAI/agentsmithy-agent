# Tool Results Lazy Loading

## Overview

This feature implements lazy loading of tool execution results to optimize LLM context usage and improve performance. Instead of storing full tool results in the dialog history, we store only references and metadata, loading full results on demand.

## Known Issues and Solutions

### Project Object Serialization
The `project` object passed in context might be serialized to a dictionary after `context_builder.build_context()`. To handle this:
- The code checks if `project` has the `dialogs_dir` attribute before using it
- The original `project` object is preserved after context building in `universal_agent.py`
- The `project` is removed from context before LLM formatting to avoid serialization

### Model Misusing get_tool_result Tool
The model might incorrectly use `get_tool_result` to retrieve results of tools it just executed. To prevent this:
- The tool description explicitly states it's for results from EARLIER in the conversation
- Clear instructions that it should NOT be used for tools just executed
- Examples of proper usage scenarios are provided
- Error messages reinforce the correct usage pattern

### Duplicate Tool Calls
The model might execute the same tool multiple times due to unclear result summaries. To prevent this:
- Tool result summaries now correctly use actual argument names from each tool
- Preview size increased from 200 to 500 characters for better context
- Preview shows complete lines instead of cutting mid-line
- Clear file paths and result counts in summaries help model understand what was executed

## Implementation Details

### 1. Tool Results Storage (`ToolResultsStorage`)

Located in `agentsmithy/core/tool_results_storage.py`, this class manages separate storage of tool results:

- **Storage Location**: `.agentsmithy/dialogs/{dialog_id}/tool_results/`
- **File Format**: JSON files named `{tool_call_id}.json` and `{tool_call_id}.meta.json`
- **Automatic Summary Generation**: Creates human-readable summaries for different tool types

### 2. Modified Tool Execution

The `ToolExecutor` now:
1. Executes tools normally
2. Stores full results using `ToolResultsStorage`
3. Creates `ToolMessage` with only references and metadata:

```json
{
  "tool_call_id": "call_abc123",
  "tool_name": "read_file",
  "status": "success",
  "metadata": {
    "size_bytes": 15420,
    "summary": "Read file: src/main.py (342 lines)",
    "truncated_preview": "import os\nimport sys\n# ... (truncated)"
  },
  "result_ref": {
    "storage_type": "tool_results",
    "dialog_id": "dialog_123",
    "tool_call_id": "call_abc123"
  }
}
```

### 3. Lazy Loading in Message Preparation

The `BaseAgent._prepare_messages()` method now supports:
- `load_tool_results=False` (default): Don't load any tool results
- `load_tool_results=True`: Load all tool results
- `load_tool_results=["call_id1", "call_id2"]`: Load specific results

Currently, full loading is not implemented due to sync/async constraints, but the infrastructure is ready.

### 4. API Endpoints

New endpoints for accessing tool results:

- `GET /api/dialogs/{dialog_id}/tool-results` - List all tool results metadata
- `GET /api/dialogs/{dialog_id}/tool-results/{tool_call_id}` - Get full tool result

### 5. Get Previous Result Tool

A new tool `get_tool_result` allows the model to retrieve previous tool results:

```python
# Usage by the model
result = await get_tool_result(tool_call_id="call_abc123")
```

## Benefits

1. **Reduced Context Usage**: Only load tool results when needed
2. **Better Performance**: Faster history loading, especially with many tool calls
3. **Flexibility**: Model can request specific results on demand
4. **Debugging**: Easy access to historical tool results via API

## Usage Examples

### For Developers

```python
# Store a tool result
storage = ToolResultsStorage(project, dialog_id)
ref = await storage.store_result(
    tool_call_id="call_123",
    tool_name="read_file",
    args={"target_file": "main.py"},
    result={"content": "...file content..."}
)

# Retrieve a tool result
result = await storage.get_result("call_123")

# List all results for a dialog
results = await storage.list_results()
```

### For the Model

When the model sees a tool result reference in the conversation history, it can retrieve the full result:

```
User: What was in the file you read earlier?
