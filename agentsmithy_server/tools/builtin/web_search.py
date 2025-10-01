from __future__ import annotations

# Local TypedDicts for type hints
from typing import Any, Literal, TypedDict

from ddgs import DDGS
from pydantic import BaseModel, Field

from agentsmithy_server.tools.core import result as result_factory
from agentsmithy_server.tools.core.types import ToolError, parse_tool_result
from agentsmithy_server.tools.registry import register_summary_for

from ..base_tool import BaseTool


class WebSearchArgsDict(TypedDict, total=False):
    query: str
    num_results: int


class WebSearchSuccess(BaseModel):
    type: Literal["web_search_result"] = "web_search_result"
    query: str
    results: list[dict[str, str]]
    count: int


WebSearchResult = WebSearchSuccess | ToolError

# Summary registration is declared above with imports


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query to look up on the web")
    num_results: int = Field(5, description="Number of search results to return")


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web for information using DuckDuckGo search engine"
    args_schema: type[BaseModel] | dict[str, Any] | None = WebSearchArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        query = kwargs["query"]
        num_results = kwargs.get("num_results", 5)

        try:
            import asyncio as _asyncio

            def run_sync() -> list[dict[str, str]]:
                local_results: list[dict[str, str]] = []
                with DDGS() as ddgs:
                    results_list = ddgs.text(query, max_results=num_results)
                    for result in results_list:
                        local_results.append(
                            {
                                "title": result.get("title", ""),
                                "url": result.get("href", result.get("link", "")),
                                "snippet": result.get(
                                    "body", result.get("snippet", "")
                                ),
                            }
                        )
                return local_results

            results = await _asyncio.to_thread(run_sync)

            return {
                "type": "web_search_result",
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            err = result_factory.error(
                "web_search",
                code="exception",
                message=f"Error performing web search: {str(e)}",
                error_type=type(e).__name__,
                details={"query": query},
            )
            err["query"] = query
            return err


@register_summary_for(WebSearchTool)
def _summarize_web_search(args: WebSearchArgsDict, result: dict[str, Any]) -> str:
    r = parse_tool_result(result, WebSearchSuccess)
    if isinstance(r, ToolError):
        return f"'{args.get('query')}': {r.error}"
    return f"'{r.query}': {r.count} results"
