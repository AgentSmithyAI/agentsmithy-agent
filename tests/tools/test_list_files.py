from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.list_files import ListFilesTool


pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_list_files_hidden_flag(tmp_path: Path):
    (tmp_path / "visible").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible" / "a.txt").write_text("ok", encoding="utf-8")
    (tmp_path / ".hidden" / "secret.txt").write_text("x", encoding="utf-8")

    t = ListFilesTool()
    res = await _run(t, path=str(tmp_path), recursive=False)
    items = res["items"]
    assert any("visible" in p for p in items)
    assert all("/.hidden" not in p for p in items)

    res2 = await _run(t, path=str(tmp_path), recursive=True, hidden_files=True)
    items2 = res2["items"]
    assert any("/.hidden" in p for p in items2)


