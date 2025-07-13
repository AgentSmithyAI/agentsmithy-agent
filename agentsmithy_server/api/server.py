"""FastAPI server for AgentSmithy."""

import json
import asyncio
from typing import Dict, Any, List, AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from agentsmithy_server.config import settings
from agentsmithy_server.core.agent_graph import AgentOrchestrator


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    context: Dict[str, Any] = {}
    stream: bool = True


class ChatResponse(BaseModel):
    content: str
    done: bool = False
    metadata: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "agentsmithy-server"


# Initialize FastAPI app
app = FastAPI(
    title="AgentSmithy Server",
    description="AI agent server similar to Cursor, powered by LangGraph",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator
orchestrator = AgentOrchestrator()


async def generate_sse_events(
    query: str,
    context: Dict[str, Any]
) -> AsyncIterator[str]:
    """Generate SSE events for streaming response."""
    try:
        # Process request with streaming
        result = await orchestrator.process_request(
            query=query,
            context=context,
            stream=True
        )
        
        graph_execution = result["graph_execution"]
        
        # Stream intermediate updates
        async for state in graph_execution:
            # Send task type when classified
            if state.get("task_type") and not state.get("response"):
                yield f'data: {{"type": "classification", "task_type": "{state["task_type"]}"}}\n\n'
            
            # Stream the response if it's an async generator
            if state.get("response"):
                if hasattr(state["response"], "__aiter__"):
                    # It's an async generator (streaming response)
                    async for chunk in state["response"]:
                        yield f'data: {{"content": "{json.dumps(chunk)[1:-1]}"}}\n\n'
                else:
                    # It's a complete response
                    yield f'data: {{"content": "{json.dumps(state["response"])[1:-1]}"}}\n\n'
        
        # Send completion signal
        yield 'data: {"done": true}\n\n'
        
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        yield f'data: {{"error": "{error_msg}"}}\n\n'


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Handle chat requests with optional streaming."""
    try:
        # Extract the latest user message
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        if request.stream:
            # Return SSE streaming response
            return EventSourceResponse(
                generate_sse_events(user_message, request.context)
            )
        else:
            # Return regular JSON response
            result = await orchestrator.process_request(
                query=user_message,
                context=request.context,
                stream=False
            )
            
            return ChatResponse(
                content=result["response"],
                done=True,
                metadata=result["metadata"]
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


@app.get("/")
async def root():
    """Root endpoint with usage information."""
    return {
        "title": "AgentSmithy Server",
        "description": "AI agent server similar to Cursor, powered by LangGraph",
        "endpoints": {
            "POST /api/chat": "Main chat endpoint (supports SSE streaming)",
            "GET /health": "Health check"
        },
        "usage": {
            "example_request": {
                "messages": [{"role": "user", "content": "Help me refactor this code"}],
                "context": {
                    "current_file": {
                        "path": "example.py",
                        "language": "python",
                        "content": "def calculate(x, y): return x + y"
                    }
                },
                "stream": True
            }
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    print(f"Starting AgentSmithy Server...")
    print(f"Server will be available at http://{settings.server_host}:{settings.server_port}")
    
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.server_port,
        reload=True
    ) 