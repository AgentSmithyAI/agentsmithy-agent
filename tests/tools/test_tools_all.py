from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.delete_file import DeleteFileTool
from agentsmithy_server.tools.list_files import ListFilesTool
from agentsmithy_server.tools.patch_file import PatchFileTool
from agentsmithy_server.tools.read_file import ReadFileTool
from agentsmithy_server.tools.replace_in_file import ReplaceInFileTool
from agentsmithy_server.tools.search_files import SearchFilesTool
from agentsmithy_server.tools.write_file import WriteFileTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_read_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    t = ReadFileTool()
    res = await _run(t, path=str(f))
    assert res["type"] == "read_file_result"
    assert res["content"] == "hello"


async def test_write_file_creates_and_overwrites(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "b.txt"
    t = WriteFileTool()
    await _run(t, path=str(f), content="one")
    assert f.read_text(encoding="utf-8") == "one"
    await _run(t, path=str(f), content="two")
    assert f.read_text(encoding="utf-8") == "two"


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


async def test_replace_in_file_placeholder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "d.txt"
    f.write_text("abc", encoding="utf-8")
    t = ReplaceInFileTool()
    res = await _run(
        t, path=str(f), diff="""<<<<<<< SEARCH\nabc\n+++++++ REPLACE\ndef\n>>>>>>>\n"""
    )
    assert res["type"] == "replace_file_request"
    assert res["path"].endswith("d.txt")


async def test_list_files_hidden_flag(tmp_path: Path):
    (tmp_path / "x").mkdir()
    (tmp_path / ".y").mkdir()
    (tmp_path / "x" / "k.txt").write_text("1", encoding="utf-8")
    (tmp_path / ".y" / "h.txt").write_text("1", encoding="utf-8")
    t = ListFilesTool()
    res = await _run(t, path=str(tmp_path), recursive=True)
    assert all("/.y" not in p for p in res["items"])  # hidden excluded
    res2 = await _run(t, path=str(tmp_path), recursive=True, hidden_files=True)
    assert any("/.y" in p for p in res2["items"])  # hidden included


async def test_search_files_regex(tmp_path: Path):
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "m.py"
    f.write_text("a\nmagic\nc\n", encoding="utf-8")
    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex="magic", file_pattern="**/*.py")
    assert any(r["file"].endswith("m.py") for r in res["results"])  # found


async def test_delete_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "z.txt"
    f.write_text("bye", encoding="utf-8")
    t = DeleteFileTool()
    res = await _run(t, path=str(f))
    assert res["type"] == "delete_file_result"
    assert not f.exists()
