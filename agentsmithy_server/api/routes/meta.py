from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    return {
        "title": "AgentSmithy Server",
        "description": "AI coding assistant server with LangGraph orchestration and RAG-powered context",
        "endpoints": {
            "POST /api/chat": "Main chat endpoint (supports SSE streaming)",
            "GET /health": "Health check",
        },
        "usage": {
            "example_request": {
                "messages": [{"role": "user", "content": "Help me refactor this code"}],
                "context": {
                    "current_file": {
                        "path": "example.py",
                        "language": "python",
                        "content": "def calculate(x, y): return x + y",
                    }
                },
                "stream": True,
            }
        },
    }
