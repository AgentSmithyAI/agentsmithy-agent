"""FastAPI server for AgentSmithy."""

import json
import asyncio
import time
from typing import Dict, Any, List, AsyncIterator, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from agentsmithy_server.config import settings
from agentsmithy_server.core.agent_graph import AgentOrchestrator
from agentsmithy_server.utils.logger import api_logger


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
) -> AsyncIterator[Dict[str, Any]]:  # Changed return type
    """Generate SSE events for streaming response."""
    api_logger.info("Starting SSE event generation", query=query[:100])
    
    try:
        # Process request with streaming
        api_logger.debug("Processing request with orchestrator", streaming=True)
        result = await orchestrator.process_request(
            query=query,
            context=context,
            stream=True
        )
        
        graph_execution = result["graph_execution"]
        api_logger.debug("Graph execution started")
        
        # Stream intermediate updates
        event_count = 0
        
        async for state in graph_execution:
            event_count += 1
            api_logger.debug(f"Processing state #{event_count}", state_keys=list(state.keys()))
            
            # Send task type when classified
            if state.get("task_type") and not state.get("response"):
                event_dict = {
                    "data": json.dumps({"type": "classification", "task_type": state["task_type"]})
                }
                api_logger.stream_log("classification", state["task_type"], event_number=event_count)
                yield event_dict
            
            # Check for task_type in classifier state
            if "classifier" in state and isinstance(state["classifier"], dict):
                classifier_data = state["classifier"]
                if "task_type" in classifier_data and classifier_data["task_type"]:
                    event_dict = {
                        "data": json.dumps({"type": "classification", "task_type": classifier_data["task_type"]})
                    }
                    yield event_dict
            
            # Stream the response if it's an async generator
            if state.get("response"):
                api_logger.debug("Processing response", has_aiter=hasattr(state["response"], "__aiter__"))
                
                if hasattr(state["response"], "__aiter__"):
                    # It's an async generator (streaming response)
                    chunk_count = 0
                    async for chunk in state["response"]:
                        chunk_count += 1
                        event_dict = {"data": chunk}  # Send raw chunk
                        api_logger.stream_log("content_chunk", chunk, chunk_number=chunk_count)
                        yield event_dict
                    api_logger.info(f"Finished streaming {chunk_count} chunks")
                else:
                    # It's a complete response
                    event_dict = {"data": state["response"]}
                    api_logger.stream_log("content_complete", state["response"])
                    yield event_dict
            
            # Check for response in agent-specific keys
            for key in state.keys():
                if key.endswith("_agent") and state[key] and key != "response":
                    agent_data = state[key]
                    if isinstance(agent_data, dict) and "response" in agent_data:
                        response = agent_data["response"]
                        
                        if hasattr(response, "__aiter__"):
                            chunk_count = 0
                            async for chunk in response:
                                chunk_count += 1
                                event_dict = {"data": chunk}
                                yield event_dict
                            api_logger.info(f"Finished streaming {chunk_count} chunks from {key}")
                        elif asyncio.iscoroutine(response):
                            # It's a coroutine that returns an async generator
                            actual_response = await response
                            
                            if hasattr(actual_response, "__aiter__"):
                                chunk_count = 0
                                async for chunk in actual_response:
                                    chunk_count += 1
                                    event_dict = {"data": chunk}
                                    yield event_dict
                                api_logger.info(f"Finished streaming {chunk_count} chunks from {key}")
                            else:
                                # Non-streaming response
                                event_dict = {"data": actual_response}
                                yield event_dict
        
        # Send completion signal
        api_logger.info("SSE generation completed", total_events=event_count)
        completion_dict = {"data": json.dumps({"done": True})}
        yield completion_dict
        
    except Exception as e:
        api_logger.error("Error in SSE generation", exception=e)
        error_msg = f"Error processing request: {str(e)}"
        error_dict = {"data": json.dumps({"error": error_msg})}
        api_logger.error(f"Yielding error event: {error_dict}")
        yield error_dict


@app.post("/api/chat")
async def chat(request: ChatRequest, raw_request: Request):
    """Handle chat requests with optional streaming."""
    start_time = time.time()
    client_host = raw_request.client.host if raw_request.client else "unknown"
    
    api_logger.info(
        "Chat request received",
        client=client_host,
        streaming=request.stream,
        message_count=len(request.messages),
        has_context="current_file" in request.context
    )
    
    try:
        # Extract the latest user message
        user_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            api_logger.warning("No user message found in request")
            raise HTTPException(status_code=400, detail="No user message found")
        
        api_logger.debug("User message extracted", message_length=len(user_message))
        
        if request.stream:
            # Return SSE streaming response
            api_logger.info("Returning SSE streaming response")
            response = EventSourceResponse(
                generate_sse_events(user_message, request.context),
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                }
            )
            
            # Log response time
            duration_ms = (time.time() - start_time) * 1000
            api_logger.request_log("POST", "/api/chat", 200, duration_ms, streaming=True)
            
            return response
        else:
            # Return regular JSON response
            api_logger.info("Processing non-streaming request")
            result = await orchestrator.process_request(
                query=user_message,
                context=request.context,
                stream=False
            )
            
            response = ChatResponse(
                content=result["response"],
                done=True,
                metadata=result["metadata"]
            )
            
            # Log response time
            duration_ms = (time.time() - start_time) * 1000
            api_logger.request_log(
                "POST", 
                "/api/chat", 
                200, 
                duration_ms, 
                streaming=False,
                response_length=len(result["response"])
            )
            
            return response
    
    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        api_logger.error("Chat request failed", exception=e, duration_ms=duration_ms)
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