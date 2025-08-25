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


@pytest.mark.parametrize(
    "diff_text",
    [
        # Simple one block
        """<<<<<<< SEARCH\nfoo\n+++++++ REPLACE\nbar\n>>>>>>>\n""",
        # Multiple blocks
        """<<<<<<< SEARCH\nA\n+++++++ REPLACE\nB\n>>>>>>>\n<<<<<<< SEARCH\nC\n+++++++ REPLACE\nD\n>>>>>>>\n""",
        # Content with regex metachars (should be treated literally by our pipeline)
        r"""<<<<<<< SEARCH\n^start.*(group)?\b|alt\n+++++++ REPLACE\n(re)placed\n>>>>>>>\n""",
        # Lookarounds and escapes
        r"""<<<<<<< SEARCH\n(?<=foo)bar and foo(?=bar) and foo\|bar\n+++++++ REPLACE\n<<ok>>\n>>>>>>>\n""",
        # Triple backticks fenced content
        """<<<<<<< SEARCH\n```js\nconsole.log('x')\n```\n+++++++ REPLACE\n```ts\nconsole.log('y')\n```\n>>>>>>>\n""",
        # XML-like tags inside content
        """<<<<<<< SEARCH\n<node attr="1">\n</node>\n+++++++ REPLACE\n<node attr="2"/>\n>>>>>>>\n""",
        # Markers at file edges (no trailing newline)
        """<<<<<<< SEARCH\nedge\n+++++++ REPLACE\nEDGE\n>>>>>>>""",
    ],
)
async def test_replace_in_file_diff_is_preserved(tmp_path: Path, monkeypatch, diff_text: str):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "e.txt"
    f.write_text("seed", encoding="utf-8")
    t = ReplaceInFileTool()
    res = await t.arun({"path": str(f), "diff": diff_text})
    assert res["type"] == "replace_file_request"
    assert res["path"].endswith("e.txt")
    # Ensure we don't mangle diff payload
    assert res["diff"] == diff_text


