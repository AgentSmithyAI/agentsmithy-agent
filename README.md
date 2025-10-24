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

- 🤖 Intelligent agent (LangGraph) that plans multi-step actions
- 📚 RAG context on your project (ChromaDB)
- 🔄 Real-time streaming replies (SSE)
- 🧰 Practical tools: file edits, search, project inspection
- 🔌 Multiple LLM providers (OpenAI supported)
- 💬 Conversation history and resumable sessions
- ⏮️ Checkpoints & rollback of file changes

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

