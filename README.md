# AgentSmithy Local Server

[![GitHub release](https://img.shields.io/github/v/release/AgentSmithyAI/agentsmithy-agent)](https://github.com/AgentSmithyAI/agentsmithy-agent/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![CI](https://github.com/AgentSmithyAI/agentsmithy-agent/actions/workflows/workflow.yaml/badge.svg?branch=master)](https://github.com/AgentSmithyAI/agentsmithy-agent/actions/workflows/workflow.yaml)
[![codecov](https://codecov.io/gh/AgentSmithyAI/agentsmithy-agent/branch/master/graph/badge.svg)](https://codecov.io/gh/AgentSmithyAI/agentsmithy-agent)
[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://www.python.org/)

A local AI server similar to Cursor, built using LangGraph for orchestration, RAG for contextualization, and SSE streaming.

## Documentation

- See the documentation in [docs/](./docs).
- SSE protocol details (current): [docs/sse-protocol.md](./docs/sse-protocol.md)

## Formatting, Linting & Tests

- Black format check: `black --check .`
- Black autofix: `black .`
- isort check: `isort --check-only .`
- isort autofix: `isort .`
- Ruff linting: `ruff check .`
- Type checking (MyPy): `mypy agentsmithy_server`
- Unit tests (pytest):
  - Run once: `pytest -v`
  - With coverage: `pytest --cov=agentsmithy_server --cov-report=term-missing`

Or use Makefile shortcuts:
- `make format` - Run black and isort
- `make lint` - Run ruff
- `make typecheck` - Run mypy
- `make test` - Run pytest

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

2. Create a virtual environment (option A: Makefile-managed):
```bash
make install         # creates .venv and installs requirements
make install-dev     # optional: adds dev tooling (ruff, black, mypy, pytest)
```

Or create it manually (option B):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies (skip if you used `make install`):
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
# SERVER_PORT=8765              # base port; actual port may auto-increment
# LOG_FORMAT=pretty             # or json
# SERVER_RELOAD=false           # enable hot-reload in dev with true
```

## Usage

### Starting the Server

```bash
# Basic usage
python main.py --workdir /abs/path/to/workspace

# With IDE specification (recommended for better context)
python main.py --workdir /abs/path/to/workspace --ide cursor
python main.py --workdir /abs/path/to/workspace --ide vscode
python main.py --workdir /abs/path/to/workspace --ide jetbrains
```

The server starts at base port `8765` (auto-increments if busy). Check startup logs for the actual URL, e.g., `http://localhost:8765`.

Notes:
- `--workdir` should point to the project directory you want to work with. The server stores state in `<workdir>/.agentsmithy`.
- If a server is already running for the same project, startup will abort with a helpful message.

### Startup Parameters

- `--workdir` (required): absolute path to the project directory. On startup, the server ensures `/abs/path/to/workspace/.agentsmithy` exists. Project-specific data (e.g., RAG index, dialogs, status.json) is stored under each project's `.agentsmithy` directory. The server keeps this path in-process; no env var is used.

- `--ide` (optional): IDE identifier to provide better context to the AI agent. Common values: `cursor`, `vscode`, `jetbrains`, `vim`, `emacs`, `sublime`. If not specified, the agent will see "unknown IDE". This parameter is runtime-only and not saved to configuration. The agent receives environment information (OS, shell, IDE) in its system prompt, allowing it to provide IDE-specific advice and use appropriate commands for your platform.

### Projects and RAG Storage

- Workspace root state: `<workdir>/.agentsmithy`
- Per-project state: `<workdir>/.agentsmithy`
- RAG (ChromaDB) persistence per project: `<workdir>/.agentsmithy/rag/chroma_db`

### Testing the API

#### Streaming request (SSE):
```bash
curl -X POST http://localhost:8765/api/chat \
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
curl -X POST http://localhost:8765/api/chat \
     -H "Content-Type: application/json" \
     -d '{
       "messages": [
         {"role": "user", "content": "Explain this function"}
       ],
       "stream": false
     }'
```

#### Browser/Node streaming client example
The endpoint is `POST /api/chat` (SSE over POST). Use `fetch` with a streaming reader:

```javascript
// Browser example
const res = await fetch('http://localhost:8765/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  },
  body: JSON.stringify({
    messages: [{ role: 'user', content: 'Help me refactor this code' }],
    stream: true,
  }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  for (const chunk of buffer.split('\n\n')) {
    if (!chunk.trim()) continue;
    if (!chunk.startsWith('data: ')) continue;
    const json = JSON.parse(chunk.slice(6));
    // handle events by json.type
  }
  buffer = '';
}
```

## API Endpoints

### POST /api/chat
Main chat endpoint (supports SSE when `Accept: text/event-stream` and `stream: true`).

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

### Dialogs API
Manage per-project conversations persisted under `<workdir>/.agentsmithy/dialogs`.

- `GET /api/dialogs`
- `POST /api/dialogs`
- `GET /api/dialogs/current`
- `PATCH /api/dialogs/current?id=<id>`
- `GET /api/dialogs/{dialog_id}`
- `PATCH /api/dialogs/{dialog_id}`
- `DELETE /api/dialogs/{dialog_id}`

## Development

### Tooling

- Linters/formatters: Ruff + Black + isort
- Type checking: mypy
- Tests: pytest

### Setup (recommended)

```bash
# create .venv and install runtime deps
make install

# install dev tools (ruff, black, mypy, pytest)
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

2. Instantiate your provider directly where needed:
```python
provider = YourLLMProvider(...)
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
├── .env.example             # Copy to .env and fill values
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

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

Copyright 2025 Alexander Morozov
