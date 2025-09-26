# Web Search Tool

## Overview

The `WebSearchTool` enables AI agents to search the web using DuckDuckGo search engine. This tool is useful for retrieving real-time information, current events, or any data that might not be available in the agent's training data.

## Features

- **Free Web Search**: Uses DuckDuckGo API without requiring API keys
- **Async Support**: Runs synchronous searches in a thread pool for async compatibility
- **Streaming Events**: No dedicated SSE event; rely on `tool_call` and subsequent `chat` updates
- **Rate Limiting**: Handles rate limits gracefully with appropriate error messages

## Installation

The web search functionality requires the `duckduckgo-search` library:

```bash
pip install duckduckgo-search==7.1.1
```

This dependency is already included in the project's `requirements.txt`.

### Usage

The tool is automatically registered in the builtin registry and available to all agents:

```python
from agentsmithy_server.tools import build_registry

registry = build_registry()
```

## Tool Arguments

- `query` (required): The search query string
- `num_results` (optional): Number of results to return (default: 5)

## Response Format

### Success Response
```json
{
    "type": "web_search_result",
    "query": "Python programming tutorials",
    "results": [
        {
            "title": "Python Tutorial - W3Schools",
            "url": "https://www.w3schools.com/python/",
            "snippet": "Well organized and easy to understand Web building tutorials..."
        }
    ],
    "count": 5
}
```

### Error Response
```json
{
    "type": "web_search_error",
    "query": "Python programming tutorials",
    "error": "Error message",
    "error_type": "ExceptionType"
}
```

## Streaming

When `web_search` is invoked, the stream includes a `tool_call` for `web_search`. The search results are returned in the tool result and summarized via `chat` messages; no `search` SSE event is emitted.

## Rate Limiting

DuckDuckGo may impose rate limits on searches. The tool handles these gracefully and returns an appropriate error message. In production environments, consider:

1. Implementing request caching
2. Adding delays between searches
3. Using multiple search backends as fallbacks

## Testing

The tool includes comprehensive unit tests with mocked dependencies. Run tests with:

```bash
pytest tests/tools/test_web_search.py -v
```

## Future Enhancements

- Support for multiple search backends (Google, Bing, etc.)
- Result caching to reduce API calls
- Advanced search filters (date range, language, region)
- Image and news search capabilities
