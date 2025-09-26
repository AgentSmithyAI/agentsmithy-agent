# Tool Results Storage Design

## Overview

This document describes the design for lazy-loading tool results to optimize LLM context usage and improve history performance.

## Problem Statement

Currently, tool execution results are stored directly in dialog history as `ToolMessage` objects with full JSON content. This causes:

1. **Context bloat**: Large tool results (e.g., file reads) consume excessive LLM tokens
2. **Performance issues**: Loading full history becomes slow with many tool calls
3. **Memory usage**: Full results are loaded even when not needed

## Proposed Solution

### 1. Tool Results Storage

Create a separate storage system for tool results:

```python
# agentsmithy_server/core/tool_results_storage.py
class ToolResultsStorage:
    """Stores tool execution results separately from dialog history."""
    
    def __init__(self, project: Project, dialog_id: str):
        self.storage_dir = project.dialogs_dir / dialog_id / "tool_results"
        
    async def store_result(
        self, 
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        timestamp: datetime
    ) -> ToolResultReference:
        """Store tool result and return reference."""
        
    async def get_result(self, tool_call_id: str) -> dict[str, Any] | None:
        """Retrieve full tool result by ID."""
        
    async def get_metadata(self, tool_call_id: str) -> ToolResultMetadata | None:
        """Get only metadata without full result."""
```

### 2. Modified History Storage

Instead of storing full results in `ToolMessage`, store only references:

```python
# Modified ToolMessage content structure
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

Modify `BaseAgent._prepare_messages()` to handle tool results intelligently:

```python
def _prepare_messages(
    self, 
    query: str, 
    context: dict[str, Any],
    load_tool_results: bool | list[str] = False
) -> list[BaseMessage]:
    """
    Args:
        load_tool_results: 
            - False: Don't load any tool results (default)
            - True: Load all tool results
            - list[str]: Load specific tool_call_ids
    """
```

### 4. API Endpoint for Tool Results

Add endpoint to retrieve tool results on demand:

```python
# GET /api/dialogs/{dialog_id}/tool-results/{tool_call_id}
@router.get("/api/dialogs/{dialog_id}/tool-results/{tool_call_id}")
async def get_tool_result(
    dialog_id: str,
    tool_call_id: str,
    project: Project = Depends(get_project)
) -> ToolResultResponse:
    """Retrieve full tool execution result."""
```

### 5. Tool for Model to Request Previous Results

Add a new tool that allows the model to retrieve previous tool results:

```python
# agentsmithy_server/tools/get_tool_result.py
class GetPreviousResultTool(BaseTool):
    """Retrieve results from previous tool executions in this dialog."""
    
    name: str = "get_tool_result"
    description: str = "Retrieve the full result of a previous tool execution"
    
    async def _arun(self, tool_call_id: str) -> dict[str, Any]:
        """Fetch previous tool result by ID."""
```

## Implementation Plan

### Phase 1: Storage Infrastructure
1. Create `ToolResultsStorage` class
2. Add storage directory structure under dialogs
3. Implement store/retrieve methods with JSON file storage

### Phase 2: Modify Tool Execution Flow
1. Update `ToolExecutor` to store results via `ToolResultsStorage`
2. Modify `ToolMessage` creation to use references instead of full results
3. Update `ChatService` to handle new message format

### Phase 3: Smart Loading
1. Modify `BaseAgent._prepare_messages()` to support lazy loading
2. Add heuristics for automatic loading (e.g., recent results, small results)
3. Implement summary generation for large results

### Phase 4: API and Tools
1. Create REST endpoint for retrieving tool results
2. Implement `get_tool_result` tool
3. Add client-side support for fetching results

## Benefits

1. **Reduced Context Usage**: Only load tool results when needed
2. **Better Performance**: Faster history loading
3. **Flexibility**: Model can request specific results
4. **Debugging**: Easy access to historical tool results via API

## Backwards Compatibility

- Existing dialogs will continue to work (full results in history)
- New storage only applies to new tool executions
- Migration tool can be provided for existing dialogs
