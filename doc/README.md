# AgentSmithy Documentation

This directory contains comprehensive documentation for the AgentSmithy code assistant server.

## Documents

### [SSE Protocol](sse-protocol.md)
Complete specification of the Server-Sent Events protocol used for real-time communication between server and client.

**Topics covered:**
- Event types (content, diff, completion, error)
- Request/response formats
- Client implementation guide
- Error handling and recovery
- Security considerations
- Complete examples

### [Architecture](architecture.md)
Detailed overview of the system architecture after the major refactoring that simplified the agent system.

**Topics covered:**
- System components overview
- Request processing flow
- Universal agent design
- Before/after refactoring comparison
- Edit block detection logic
- Configuration and scaling

## Quick Reference

### Making a Request
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "messages": [{"role": "user", "content": "refactor this function"}],
    "context": {
      "current_file": {
        "path": "example.py",
        "content": "def old_func(): pass",
        "selection": "def old_func(): pass"
      }
    },
    "stream": true
  }'
```

### Expected Response
```
data: {"content": "I'll refactor this function:"}

data: {"type": "diff", "file": "example.py", "diff": "--- a/example.py\n+++ b/example.py\n...", "reason": "Improved naming"}

data: {"done": true}
```

### Edit Block Triggers
The system generates file diffs when:
1. ✅ User provides code context (file/selection)
2. ✅ Query contains modification keywords: refactor, fix, improve, etc.
3. ✅ Both conditions are met

## Development Setup

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Set environment**: Copy `.env.example` to `.env` and add your `OPENAI_API_KEY`
3. **Run server**: `python main.py`
4. **Test endpoint**: Visit `http://localhost:8000/docs` for interactive API documentation

## Recent Changes

### Major Refactoring (Current Version)
- ✅ **Simplified**: 6 agents → 1 universal agent
- ✅ **Removed**: Classification and routing overhead  
- ✅ **Added**: Automatic edit block detection
- ✅ **Improved**: Unified diff generation and streaming
- ✅ **Enhanced**: Error handling and logging

### Key Improvements
- **50% less code** to maintain
- **No classification delays** 
- **Consistent behavior** across all request types
- **Better edit block generation** with forced prompting
- **Cleaner SSE protocol** for client integration

## Architecture Summary

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│   Client    │───▶│  FastAPI     │───▶│ Universal     │
│   Editor    │    │  /api/chat   │    │ Agent         │
└─────────────┘    └──────────────┘    └───────────────┘
       ▲                                        │
       │           ┌──────────────┐            ▼
       └───────────│ SSE Stream   │◀───┌─────────────┐
                   │ (diffs)      │    │ LLM         │
                   └──────────────┘    │ Provider    │
                                       └─────────────┘
```

## Support

For questions about the protocol or architecture:
1. Check the specific documentation files above
2. Review the code examples in the documents
3. Test with the provided curl examples
4. Examine the FastAPI interactive docs at `/docs` 