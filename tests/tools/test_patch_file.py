from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.patch_file import PatchFileTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_patch_file_changes_lines(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "c.txt"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    t = PatchFileTool()
    await _run(
        t,
        file_path=str(f),
        changes=[
            {
                "line_start": 2,
                "line_end": 2,
                "old_content": "b",
                "new_content": "B",
                "reason": "",
            }
        ],
    )
    assert f.read_text(encoding="utf-8").splitlines()[1] == "B"
