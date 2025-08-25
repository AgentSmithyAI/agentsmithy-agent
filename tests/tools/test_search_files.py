from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.search_files import SearchFilesTool


pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_search_files_matches_and_context(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    f = d / "main.py"
    f.write_text("""
line1
needle here
line3
line4
""".strip(), encoding="utf-8")

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex="needle", file_pattern="**/*.py")
    results = res["results"]
    assert len(results) == 1
    assert results[0]["file"].endswith("main.py")
    assert "needle here" in results[0]["context"]


