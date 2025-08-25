from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.delete_file import DeleteFileTool


pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_delete_file_removes_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "z.txt"
    f.write_text("bye", encoding="utf-8")
    t = DeleteFileTool()
    res = await _run(t, path=str(f))
    assert res["type"] == "delete_file_result"
    assert not f.exists()


