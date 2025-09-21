from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.config import settings
from agentsmithy_server.core.events import EventFactory

from .base_tool import BaseTool


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query to look up on the web")
    num_results: int = Field(5, description="Number of search results to return")


class WebSearchTool(BaseTool):  # type: ignore[override]
    name: str = "web_search"
    description: str = "Search the web for information using DuckDuckGo search engine"
    args_schema: type[BaseModel] | dict[str, Any] | None = WebSearchArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        query = kwargs["query"]
        num_results = kwargs.get("num_results", 5)

        # Emit search event
        await self.emit_event(
            EventFactory.from_dict(
                {"type": "search", "query": query}, dialog_id=self._dialog_id
            ).to_dict()
        )

        # Import here to avoid loading the library if not used
        try:
            from duckduckgo_search import AsyncDDGS
        except ImportError:
            return {
                "type": "web_search_error",
                "query": query,
                "error": "duckduckgo-search library is not installed. Please install duckduckgo-search to enable web search.",
                "error_type": "ImportError",
            }

        try:
            results: list[dict[str, str]] = []
            async with AsyncDDGS(
                headers={"User-Agent": settings.web_user_agent}
            ) as ddgs:
                maybe_iter = ddgs.text(query, max_results=num_results)
                # Support both: returning an async iterator directly or a coroutine that resolves to it (as in tests)
                if not hasattr(maybe_iter, "__aiter__"):
                    maybe_iter = await maybe_iter
                async for result in maybe_iter:
                    results.append(
                        {
                            "title": result.get("title", ""),
                            "url": result.get("href", result.get("link", "")),
                            "snippet": result.get("body", result.get("snippet", "")),
                        }
                    )

            return {
                "type": "web_search_result",
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {
                "type": "web_search_error",
                "query": query,
                "error": f"Error performing web search: {str(e)}",
                "error_type": type(e).__name__,
            }
