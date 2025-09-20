from __future__ import annotations

import pytest

from agentsmithy_server.tools.web_fetch import WebFetchTool

pytestmark = pytest.mark.asyncio


async def test_web_fetch_runs_minimal():
    tool = WebFetchTool()
    res = await tool.arun({"url": "https://example.com"})
    assert res["type"] in {"web_browse_result", "web_browse_error"}
    assert res.get("mode") in {"http", "js"}