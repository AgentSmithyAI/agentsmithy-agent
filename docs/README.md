# Documentation

Welcome to the AgentSmithy documentation.

## Index

- [SSE Protocol](./sse-protocol.md) — POST-based SSE streaming, event taxonomy
- [Project structure and runtime files](./project-structure.md)
- [Architecture](./architecture.md)
- [Dialog History endpoint](./history-endpoint.md)
- [Checkpoints and Transactions](./checkpoints-and-transactions.md)
- [Tool results storage design](./tool-results-storage-design.md)
- [Tool results lazy loading](./tool-results-lazy-loading.md)
- [Provider configuration](./provider-configuration.md) and [OpenAI config](./openai-config.md)
- [Graceful shutdown](./graceful-shutdown.md)
- [Web search tool](./web-search-tool.md)

## Quickstart

1) Create a `.env` file in your project directory (workdir) with your configuration:

```bash
# Example .env file in your workdir
OPENAI_API_KEY=sk-your-api-key-here
# MODEL=gpt-4o
# EMBEDDING_MODEL=text-embedding-3-small
```

Alternatively, you can configure via `.agentsmithy/config.json` (see [Provider configuration](./provider-configuration.md)).

2) Start the server with your project directory as `--workdir`:

```bash
python main.py --workdir /abs/path/to/your/project
```

The server will automatically load `.env` from the workdir if it exists.

3) Send a streaming chat request:

```bash
curl -X POST http://localhost:8765/api/chat \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "messages": [{"role": "user", "content": "Help me refactor this code"}],
    "stream": true
  }'
```

## Endpoints

- `POST /api/chat` — main chat endpoint (supports SSE when `stream=true`)
- `GET /health` — health check
- Dialogs API under `/api/dialogs` for managing conversations

If you're integrating a client/editor, start with the SSE Protocol.


