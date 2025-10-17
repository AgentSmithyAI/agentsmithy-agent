# Graceful Shutdown Documentation

## Overview

AgentSmithy supports graceful shutdown, ensuring that all active SSE (Server-Sent Events) streams are properly terminated when the server receives shutdown signals (SIGINT/SIGTERM). The implementation correctly handles asynchronous generator cleanup without `GeneratorExit` errors.

## How It Works

### Signal Handling

The server registers signal handlers for:
- **SIGINT** (Ctrl+C)
- **SIGTERM** (Docker/Kubernetes termination)

When a signal is received:
1. A global `shutdown_event` is set
2. Active SSE streams are notified
3. Final events are sent to clients
4. Server waits for all streams to complete
5. Server shuts down cleanly

### SSE Stream Termination

When shutdown is initiated, active SSE streams:
1. Detect the shutdown event or cancellation
2. Handle `GeneratorExit` exceptions gracefully without yielding in cleanup
3. For `CancelledError`, may send a final done event if possible
4. Close the connection cleanly

### GeneratorExit Handling

The SSE generator (`guarded_stream` in `sse.py`) properly handles Python's `GeneratorExit` exception:
- When `GeneratorExit` is raised, the generator immediately returns without yielding
- This prevents the "async generator ignored GeneratorExit" runtime error
- The separation between `GeneratorExit` and `CancelledError` ensures proper cleanup in both cases

### Implementation Details

#### Main Components

1. **main.py**
   - Signal handlers registration
   - Global `shutdown_event` creation
   - Custom uvicorn server with graceful shutdown

2. **ChatService**
   - Tracks active streams
   - Monitors shutdown event
   - Cancels streams on shutdown

3. **FastAPI App**
   - Receives shutdown event via app.state
   - Cleanup in lifespan handler

#### Code Flow

```python
# Signal received
signal_handler() -> shutdown_event.set()

# In streaming loop
if shutdown_event.is_set():
    yield error_event
    yield done_event
    return

# Server shutdown
ChatService.shutdown() -> cancel all active streams
```

## Testing

### Manual Testing

1. Start the server:
   ```bash
   python main.py --workdir .
   ```

2. Make a streaming request:
   ```bash
   curl -X POST http://localhost:8765/api/chat \
     -H "Content-Type: application/json" \
     -H "Accept: text/event-stream" \
     -d '{"messages": [{"role": "user", "content": "Tell me a long story"}], "stream": true}'
   ```

3. Press Ctrl+C to send SIGINT

4. Observe graceful shutdown:
   - Error event sent to client
   - Done event sent to client
   - Server shuts down cleanly

### Automated Testing

Run the test scripts:
```bash
# Python test with detailed output
python test_graceful_shutdown.py

# Simple bash test
./test_shutdown_simple.sh

# API endpoint test
python test_api_endpoint.py
```

## Benefits

1. **No Hanging Connections**: Clients receive proper termination events
2. **Clean Shutdown**: Server waits for all streams to complete
3. **Error Handling**: Clients know why the stream ended
4. **Protocol Compliance**: Follows SSE protocol with error+done events

## Client Implementation

Clients should handle the shutdown scenario:

```javascript
es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'error' && data.error.includes('shutdown')) {
    console.log('Server is shutting down');
    // Handle graceful disconnection
  }
  
  if (data.type === 'done') {
    es.close();
    // Clean up resources
  }
};
```

## Configuration

No additional configuration is required. Graceful shutdown is automatically enabled.

## Troubleshooting

### Server doesn't shut down
- Check for hanging requests or connections
- Ensure all async tasks are properly awaited
- Review server logs for errors

### Clients don't receive shutdown events
- Verify SSE connection is active
- Check network proxies/load balancers timeout settings
- Ensure client properly handles error events

### Testing issues
- Ensure port 8765 is available (or the port specified in your config)
- Check .env file configuration
- Verify Python dependencies are installed
