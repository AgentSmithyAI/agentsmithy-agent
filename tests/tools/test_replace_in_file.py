from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.replace_in_file import ReplaceInFileTool


pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_replace_in_file_placeholder_returns_request(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "d.txt"
    f.write_text("abc", encoding="utf-8")
    t = ReplaceInFileTool()
    res = await _run(t, path=str(f), diff="""<<<<<<< SEARCH\nabc\n+++++++ REPLACE\ndef\n>>>>>>>\n""")
    assert res["type"] == "replace_file_request"
    assert res["path"].endswith("d.txt")


