from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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

        try:
            # Import here to avoid loading the library if not used
            import asyncio

            from duckduckgo_search import DDGS

            # Run synchronous search in thread pool
            def sync_search():
                results = []
                # Use different backend and add headers to avoid rate limiting
                with DDGS(
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                ) as ddgs:
                    # Try different backends if one fails
                    for backend in ["html", "lite"]:
                        try:
                            search_results = list(
                                ddgs.text(
                                    query, max_results=num_results, backend=backend
                                )
                            )
                            for result in search_results:
                                results.append(
                                    {
                                        "title": result.get("title", ""),
                                        "url": result.get(
                                            "href", result.get("link", "")
                                        ),
                                        "snippet": result.get(
                                            "body", result.get("snippet", "")
                                        ),
                                    }
                                )
                            if results:  # If we got results, stop trying other backends
                                break
                        except Exception:
                            continue  # Try next backend
                return results

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, sync_search)

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
