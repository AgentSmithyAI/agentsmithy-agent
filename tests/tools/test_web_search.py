"""Tests for WebSearchTool."""

import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agentsmithy_server.tools.web_search import WebSearchTool


@pytest.mark.asyncio
async def test_web_search_success():
    """Test successful web search."""
    tool = WebSearchTool()
    tool._sse_callback = AsyncMock()
    tool._dialog_id = "test-dialog"

    mock_results = [
        {
            "title": "Test Result 1",
            "href": "https://example.com/1",
            "body": "This is a test result snippet 1",
        },
        {
            "title": "Test Result 2",
            "href": "https://example.com/2",
            "body": "This is a test result snippet 2",
        },
    ]

    # Mock AsyncDDGS class used in the tool module
    mock_ddgs_instance = AsyncMock()
    mock_ddgs_class = Mock(return_value=mock_ddgs_instance)

    # Set up async context manager
    mock_ddgs_instance.__aenter__.return_value = mock_ddgs_instance
    mock_ddgs_instance.__aexit__.return_value = None

    # Create an async generator for results
    async def async_gen():
        for result in mock_results:
            yield result

    mock_ddgs_instance.text.return_value = async_gen()

    with patch("agentsmithy_server.tools.web_search.AsyncDDGS", mock_ddgs_class):
        result = await tool._arun(query="test query", num_results=2)

    assert result["type"] == "web_search_result"
    assert result["query"] == "test query"
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "Test Result 1"
    assert result["results"][0]["url"] == "https://example.com/1"
    assert result["results"][0]["snippet"] == "This is a test result snippet 1"
    assert result["count"] == 2

    # Tool no longer emits a separate SSE 'search' event
    tool._sse_callback.assert_not_called()


@pytest.mark.asyncio
async def test_web_search_import_error():
    """duckduckgo-search is mandatory; simulate ImportError should raise at import time."""
    with patch.dict(sys.modules, {"duckduckgo_search": None}):
        import importlib

        with pytest.raises(ImportError):
            import agentsmithy_server.tools.web_search as ws

            importlib.reload(ws)


@pytest.mark.asyncio
async def test_web_search_exception():
    """Test web search when an exception occurs."""
    tool = WebSearchTool()
    tool._sse_callback = AsyncMock()

    # Mock AsyncDDGS class used in the tool module
    mock_ddgs_instance = AsyncMock()
    mock_ddgs_class = Mock(return_value=mock_ddgs_instance)

    # Set up async context manager
    mock_ddgs_instance.__aenter__.return_value = mock_ddgs_instance
    mock_ddgs_instance.__aexit__.return_value = None
    mock_ddgs_instance.text.side_effect = Exception("Network error")

    with patch("agentsmithy_server.tools.web_search.AsyncDDGS", mock_ddgs_class):
        result = await tool._arun(query="test query")

    assert result["type"] == "web_search_error"
    assert result["query"] == "test query"
    assert "Network error" in result["error"]
    assert result["error_type"] == "Exception"


@pytest.mark.asyncio
async def test_web_search_default_num_results():
    """Test web search with default number of results."""
    tool = WebSearchTool()
    tool._sse_callback = AsyncMock()

    mock_results = [
        {"title": f"Result {i}", "href": f"url{i}", "body": f"snippet{i}"}
        for i in range(5)
    ]

    # Mock AsyncDDGS class used in the tool module
    mock_ddgs_instance = AsyncMock()
    mock_ddgs_class = Mock(return_value=mock_ddgs_instance)

    # Set up async context manager
    mock_ddgs_instance.__aenter__.return_value = mock_ddgs_instance
    mock_ddgs_instance.__aexit__.return_value = None

    async def async_gen():
        for result in mock_results:
            yield result

    mock_ddgs_instance.text.return_value = async_gen()

    with patch("agentsmithy_server.tools.web_search.AsyncDDGS", mock_ddgs_class):
        result = await tool._arun(query="test query")

    # Default is 5 results
    assert len(result["results"]) == 5
    assert result["count"] == 5
