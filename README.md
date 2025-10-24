# AgentSmithy — self-hosted AI coding assistant server

[![GitHub release](https://img.shields.io/github/v/release/AgentSmithyAI/agentsmithy-agent)](https://github.com/AgentSmithyAI/agentsmithy-agent/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![CI](https://github.com/AgentSmithyAI/agentsmithy-agent/actions/workflows/workflow.yaml/badge.svg?branch=master)](https://github.com/AgentSmithyAI/agentsmithy-agent/actions/workflows/workflow.yaml)
[![codecov](https://codecov.io/gh/AgentSmithyAI/agentsmithy-agent/branch/master/graph/badge.svg)](https://codecov.io/gh/AgentSmithyAI/agentsmithy-agent)
[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://www.python.org/)

AgentSmithy is a local server that brings an AI coding assistant to your IDE. It orchestrates an LLM with tools, understands your codebase via RAG, and streams responses in real time.

## What is this

- Self-hosted: runs locally as a server
- IDE-independent via plugin: currently supports [VS Code extension](https://github.com/AgentSmithyAI/agentsmithy-vscode); more IDEs planned

## Highlights

- Generate and refactor code with full awareness of your repository
- Explain unfamiliar code and trace how functions, modules, and data flow connect
- Find things fast: semantic search across code, config, and docs
- Make safe changes: preview edits, apply patches, and rollback if needed
- Fix bugs and add tests step‑by‑step with guided edits
- Answer questions about your project’s architecture and APIs
- Keep context: conversations persist across sessions

## Technical features

- Orchestration: LangGraph for stateful agent workflows (branches, retries, checkpoints)
- Tooling: LangChain tool ecosystem + custom tools for file ops, project search, and safe code edits
- RAG over code: ChromaDB vector store, LangChain text splitters/embeddings; incremental indexing
- API server: FastAPI with real‑time streaming via SSE; OpenAPI, Swagger (/docs), Redoc (/redoc)
- Safety: checkpoints and transactions for multi‑step edits with rollback capability
- Providers: multi‑LLM via LangChain (e.g., OpenAI) with environment‑based configuration
- Web search: DDGS search with Playwright fallback for JS‑rendered pages
- Observability: structured logs (structlog) and LangSmith compatibility
- Performance: uvicorn + uvloop, fully async I/O

## Learn more

- Documentation index: [docs/README.md](./docs/README.md)
- API reference (when server is running): /docs (Swagger), /redoc, /openapi.json
- Architecture overview: [docs/architecture.md](./docs/architecture.md)
- SSE protocol: [docs/sse-protocol.md](./docs/sse-protocol.md)
- Checkpoints & transactions: [docs/checkpoints-and-transactions.md](./docs/checkpoints-and-transactions.md)

## Getting started

See Quickstart in [docs/README.md](./docs/README.md). It covers env setup, running the server, and example requests.

## License

Apache 2.0 — see LICENSE.

© 2025 Alexander Morozov

