from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy.tools.builtin.write_file import WriteFileTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_write_file_create_and_overwrite(tmp_path: Path, monkeypatch):
    # Use isolated temp directory as both HOME and project root (cwd)
    # so versioning/checkpoints logic does not touch the real workspace.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "file.txt"
    t = WriteFileTool()
    await _run(t, path=str(f), content="one")
    assert f.read_text(encoding="utf-8") == "one"
    await _run(t, path=str(f), content="two")
    assert f.read_text(encoding="utf-8") == "two"
