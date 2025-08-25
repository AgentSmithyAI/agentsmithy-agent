# AgentSmithy Local Server

A local AI server similar to Cursor, built using LangGraph for orchestration, RAG for contextualization, and SSE streaming.

## Documentation

- See the documentation in [docs/](./docs).
- SSE protocol details (current): [docs/sse-protocol.md](./docs/sse-protocol.md)

## Features

- 🤖 **Universal agent** orchestrated with LangGraph
- 📚 **RAG (Retrieval-Augmented Generation)** for context handling
- 🔄 **Streaming responses** via Server-Sent Events (SSE)
- 🧰 **Tool-aware workflow** with structured SSE events (chat/reasoning/tool_call/file_edit)
- 🔌 **Flexible LLM provider interface** (OpenAI supported out of the box)
- 🗄️ **ChromaDB** vector store for context persistence

## Architecture

```mermaid
graph TD
    A[User Request] --> B[API Server<br/>FastAPI + SSE]
    B --> C[LangGraph Orchestrator]
    C --> U[Universal Agent]
    U --> R[RAG System]
    R --> K[Vector Store<br/>ChromaDB]
    U --> T[Tools<br/>ToolExecutor/ToolManager]
    U --> M[LLM<br/>OpenAI]
    M --> N[Response]
    T --> O1[SSE Events<br/>chat/reasoning/tool_call/file_edit]
    N --> O[SSE Stream]
    O1 --> O
    O --> P[Client]
```

## Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd agentsmithy-local
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with required model and API key (minimum):
```env
OPENAI_API_KEY=your_openai_api_key_here
DEFAULT_MODEL=gpt-5  # required

# Optional overrides
# DEFAULT_TEMPERATURE=0.7
# DEFAULT_EMBEDDING_MODEL=text-embedding-3-small
# MAX_TOKENS=4000
# REASONING_EFFORT=medium       # only for gpt-5 models
# REASONING_VERBOSITY=auto      # only for gpt-5 models
# SERVER_HOST=localhost
# SERVER_PORT=11434             # base port; actual port may auto-increment
# LOG_FORMAT=pretty             # or json
# SERVER_RELOAD=false           # enable hot-reload in dev with true
```

## Usage

### Starting the Server

```bash
# Start via main.py with a working directory (required)
python main.py --workdir /abs/path/to/workspace
```

The server starts at base port `11434` (auto-increments if busy). Check startup logs for the actual URL, e.g., `http://localhost:11434`.

### Startup Parameters

- `--workdir` (required): absolute path to the workspace directory. On startup, the server ensures `/abs/path/to/workspace/.agentsmithy` exists. Project-specific data (e.g., RAG index) is stored under each project's `.agentsmithy` directory inside the workspace. The server keeps this path in-process; no env var is used.

### Projects and RAG Storage

- Workspace root state: `<workdir>/.agentsmithy`
- Per-project state: `<workdir>/<project>/.agentsmithy`
- RAG (ChromaDB) persistence per project: `<workdir>/<project>/.agentsmithy/rag/chroma_db`

### Testing the API

#### Streaming request (SSE):
```bash
curl -X POST http://localhost:11434/api/chat \
     -H "Content-Type: application/json" \
     -H "Accept: text/event-stream" \
     -d '{
       "messages": [
         {"role": "user", "content": "Help me refactor this code"}
       ],
       "context": {
         "current_file": {
           "path": "example.py",
           "language": "python",
           "content": "def calculate(x, y): return x + y"
         }
       },
       "stream": true
     }'
```

#### Regular request:
```bash
curl -X POST http://localhost:11434/api/chat \
     -H "Content-Type: application/json" \
     -d '{
       "messages": [
         {"role": "user", "content": "Explain this function"}
       ],
       "stream": false
     }'
```

## API Endpoints

### POST /api/chat
Main chat endpoint.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Your question here"}
  ],
  "context": {
    "current_file": {
      "path": "file.py",
      "language": "python",
      "content": "file content",
      "selection": "selected code"
    },
    "open_files": [
      {
        "path": "other_file.py",
        "language": "python",
        "content": "content"
      }
    ]
  },
  "stream": true
}
```

**Response (streaming):**
```
data: {"type": "chat_start", "dialog_id": "01J..."}

data: {"type": "chat", "content": "I'll help you refactor ", "dialog_id": "01J..."}

data: {"type": "tool_call", "name": "read_file", "args": {"path": "example.py"}, "dialog_id": "01J..."}

data: {"type": "file_edit", "file": "/abs/path/to/example.py", "dialog_id": "01J..."}

data: {"type": "chat_end", "dialog_id": "01J..."}

data: {"type": "done", "done": true, "dialog_id": "01J..."}
```

### GET /health
Server health check.

## Development

### Tooling

- Linters/formatters: Ruff + Black
- Type checking: mypy
- Tests: pytest

### Setup (recommended)

```bash
# create venv and install runtime deps
make install

# install dev tools
make install-dev
```

### Common tasks

```bash
# format code
make format

# run linters
make lint

# type check
make typecheck

# run tests
make test
```

## Extending Functionality

### Adding a New LLM Provider

1. Create a new provider class in `agentsmithy_server/core/llm_provider.py`:
```python
class YourLLMProvider(LLMProvider):
    async def agenerate(self, messages, stream=False):
        ...
    def get_model_name(self) -> str:
        ...
    def bind_tools(self, tools: List[BaseTool]):
        ...
```

2. Register the provider:
```python
LLMFactory.register_provider("your_llm", YourLLMProvider)
```

### Adding a New Agent

The orchestrator currently routes everything to a single `UniversalAgent`. To introduce specialized agents, add your agent in `agentsmithy_server/agents/` and update `agentsmithy_server/core/agent_graph.py` to add nodes and routing.

## Project Structure

```
agentsmithy-local/
├── agentsmithy_server/
│   ├── agents/              # Agent implementations (UniversalAgent)
│   ├── api/                 # FastAPI server
│   ├── config/              # Configuration (settings, logging)
│   ├── core/                # Core components (LLM, LangGraph)
│   ├── rag/                 # RAG system
│   └── utils/               # Utilities
├── requirements.txt         # Dependencies
└── README.md               # Documentation
```

## Debugging and Diagnostics

The server includes structured logging. Pretty colored logs are used by default; set `LOG_FORMAT=json` to switch to JSON.

```bash
# Via environment variable
LOG_FORMAT=json python main.py

# Or in .env
LOG_FORMAT=json
```

### Log Output Example

When debug logging is enabled, you'll see detailed information about:
- Request processing flow
- Agent classification and routing
- SSE event generation
- Response streaming
- Error details with stack traces

Example log output:
```json
{"timestamp": "2024-01-01T12:00:00", "level": "INFO", "logger": "agentsmithy.api", "message": "Chat request received", "client": "127.0.0.1", "streaming": true}
{"timestamp": "2024-01-01T12:00:01", "level": "DEBUG", "logger": "agentsmithy.agents", "message": "Classifying task", "query_preview": "Help me refactor this code"}
{"timestamp": "2024-01-01T12:00:02", "level": "INFO", "logger": "agentsmithy.agents", "message": "Task classified", "task_type": "refactor"}
```
