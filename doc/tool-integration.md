# Tool Integration Documentation

## Overview

The AgentSmithy system now supports function calling through LangChain tools. Instead of parsing special text blocks, the UniversalAgent can now directly invoke tools to perform actions like file patching.

## Architecture Changes

### 1. New Tools Module Structure

Created a properly organized `agentsmithy_server/tools/` module with:
- `base_tool.py` - Base class for all tools, extending LangChain's `BaseTool`
- `patch_file.py` - Implementation of file patching functionality
- `tool_manager.py` - Manages tool registration and execution
- `tool_executor.py` - Handles LLM tool calls processing
- `tool_factory.py` - Factory for creating standard tool sets

### 2. PatchFileTool

The `PatchFileTool` replaces the previous edit block parsing system with a proper tool that:
- Accepts a file path and list of changes
- Creates temporary backups before modifications
- Streams change information via SSE callbacks
- Returns structured results with diffs

#### Tool Input Schema:
```python
{
    "file_path": "path/to/file.py",
    "changes": [
        {
            "line_start": 10,
            "line_end": 15,
            "old_content": "original code",
            "new_content": "improved code", 
            "reason": "Refactoring for clarity"
        }
    ]
}
```

### 3. ToolManager

Central component for tool management:
- Registers and stores tools in a registry
- Provides tool lookup by name
- Executes tools with error handling
- Manages SSE callbacks for all tools
- Supports batch tool execution

### 4. ToolExecutor

Handles the interaction between LLM and tools:
- Binds tools to LLM for function calling
- Processes streaming and non-streaming responses
- Reconstructs tool calls from streaming chunks
- Executes tools via ToolManager
- Formats responses for the agent

### 5. ToolFactory

Factory pattern for tool creation:
- Creates default tool sets
- Initializes ToolManager with tools
- Supports custom tool registration
- Provides standard tool configurations

### 6. UniversalAgent Updates

The UniversalAgent now has a cleaner architecture:
- Uses ToolFactory to create tool manager
- Delegates tool processing to ToolExecutor
- Simplified process method
- Clear separation of concerns
- Supports SSE callbacks for real-time updates

### 7. LLMProvider Enhancement

Added `bind_tools()` method to LLMProvider:
- Abstract method in base class
- OpenAI implementation uses LangChain's native tool binding
- Returns LLM instance with tools attached

### 8. SSE Integration

Enhanced SSE streaming to support tool events:
- AgentOrchestrator can set SSE callbacks
- Tools can stream events during execution
- Server queues and delivers tool events alongside content

## Usage Example

When the user requests code changes, the LLM will now generate tool calls:

```json
{
    "tool_calls": [{
        "name": "patch_file",
        "args": {
            "file_path": "example.py",
            "changes": [{
                "line_start": 1,
                "line_end": 3,
                "old_content": "def old_func():\n    pass",
                "new_content": "def new_func():\n    \"\"\"Improved function.\"\"\"\n    pass",
                "reason": "Added docstring"
            }]
        }
    }]
}
```

## Component Architecture

```
UniversalAgent
    ├── ToolManager (manages tool registry)
    │   ├── PatchFileTool
    │   └── (future tools...)
    ├── ToolExecutor (processes LLM responses)
    │   ├── Binds tools to LLM
    │   ├── Handles streaming/non-streaming
    │   └── Executes tool calls
    └── LLMProvider (with bind_tools support)
```

## Code Example

```python
# Creating an agent with tools
from agentsmithy_server.agents import UniversalAgent
from agentsmithy_server.tools import ToolFactory
from agentsmithy_server.core import LLMFactory

# Agent automatically initializes with default tools
agent = UniversalAgent(
    llm_provider=LLMFactory.create("openai"),
    context_builder=ContextBuilder()
)

# Tools are managed internally
# ToolFactory creates: ToolManager -> registers PatchFileTool
# ToolExecutor handles all tool-related processing

# Process a request - tools are invoked automatically
result = await agent.process(
    query="Add type hints to this function",
    context={"current_file": {...}},
    stream=False
)
```

## Benefits

1. **Clean Architecture**: Clear separation of concerns with dedicated components
2. **Structured Execution**: Tools provide type-safe, validated inputs
3. **Better Error Handling**: Tool execution can be wrapped with proper error handling
4. **Streaming Updates**: SSE callbacks enable real-time progress updates
5. **Extensibility**: Easy to add new tools following the same pattern
6. **LLM Integration**: Leverages native function calling capabilities
7. **Maintainability**: Each component has a single responsibility

## Adding New Tools

To add a new tool:

1. Create a tool class extending `BaseTool`:
```python
from agentsmithy_server.tools import BaseTool

class MyCustomTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    
    async def _arun(self, **kwargs):
        # Tool implementation
        return result
```

2. Register it in ToolFactory's default tools:
```python
# In tool_factory.py
@staticmethod
def create_default_tools() -> List[BaseTool]:
    tools = []
    tools.append(PatchFileTool())
    tools.append(MyCustomTool())  # Add your tool
    return tools
```

## Migration Notes

- The old edit block parsing code has been removed
- System prompts updated to instruct LLM to use tools
- Response structure now includes tool_calls and tool_results
- File operations are executed through tools rather than post-processing
- All tool logic is now properly encapsulated in the tools module

## Technical Implementation Details

### Async Generator Handling

The tool executor properly handles both streaming and non-streaming modes:
- **Streaming**: `process_with_tools(stream=True)` returns an async generator directly
- **Non-streaming**: `process_with_tools_async()` returns an awaitable result

This design avoids the "object async_generator can't be used in 'await' expression" error by:
1. Separating streaming and non-streaming code paths
2. Returning the async generator directly without awaiting in streaming mode
3. Using a dedicated async method for non-streaming operations

### Multiple Changes Handling in PatchFileTool

The patch tool handles multiple changes correctly by:

1. **Sorting changes in reverse order by line number** - This prevents index shifting issues
2. **Creating a single backup before any changes** - Ensures data safety
3. **Applying changes from bottom to top** - Earlier changes don't affect later line numbers

Example:
```python
# Changes are sorted: line 7-8, line 4-5, line 1-2
# Applied in reverse order so indices remain valid
# Result: All changes applied successfully
```

Benefits:
- No complex offset tracking needed
- Simple and predictable behavior
- All changes use original line numbers from the request

### Important Limitations

**All line numbers must refer to the ORIGINAL file state:**

1. **Line numbers are absolute** - they refer to positions in the original file before ANY changes
2. **Changes that add/remove lines** will shift subsequent content, but you must still use original line numbers
3. **Cannot reference non-existent lines** - if the original file has 7 lines, you cannot patch line 8

### Common Issues

**Problem**: "Content mismatch at lines X-X" when X is beyond the original file length
- **Cause**: After applying changes that add lines, the file grows, but the patch still references original positions
- **Solution**: Ensure all line numbers are valid for the ORIGINAL file

**Problem**: "Invalid line range" 
- **Cause**: Trying to patch a line that doesn't exist in the original file
- **Solution**: Check the original file length before specifying line numbers

### Best Practices

1. **Always base line numbers on the original file state**
2. **Be aware that insertions will shift content down**
3. **When patching multiple locations, remember they all reference the SAME original state**
4. **If you need to apply changes based on intermediate states, split into multiple tool calls**

### Example of the Problem

Original file (7 lines):
```
1: def func1():
2:     pass
3: 
4: def func2():
5:     pass
6: 
7: # comment
```

Changes requested:
1. Add print to func1 (line 2)
2. Add print to func2 (line 5)
3. Modify something on line 8 ← **WILL FAIL: line 8 doesn't exist!**

Even though after the first two changes the file will have 9 lines, you cannot reference line 8 because it doesn't exist in the ORIGINAL file.
