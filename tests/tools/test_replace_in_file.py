from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.replace_in_file import ReplaceInFileTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_replace_in_file_search_replace_applies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "d.txt"
    f.write_text("abc", encoding="utf-8")
    t = ReplaceInFileTool()
    res = await _run(
        t, path=str(f), diff="""------- SEARCH
abc
=======
def
+++++++ REPLACE
"""
    )
    assert res["type"] == "replace_file_result"
    assert f.read_text(encoding="utf-8") == "def"


@pytest.mark.parametrize(
    ("initial", "diff_text", "expected"),
    [
        ("foo", """------- SEARCH
foo
=======
bar
+++++++ REPLACE
""", "bar"),
        (
            "A\nC\n",
            """------- SEARCH
A
=======
B
+++++++ REPLACE
------- SEARCH
C
=======
D
+++++++ REPLACE
""",
            "B\nD\n",
        ),
        (
            "^start.*(group)?\\b|alt\n",
            r"""------- SEARCH
^start.*(group)?\b|alt
=======
(re)placed
+++++++ REPLACE
""",
            "(re)placed\n",
        ),
        (
            "(?<=foo)bar and foo(?=bar) and foo|bar\n",
            r"""------- SEARCH
(?<=foo)bar and foo(?=bar) and foo\|bar
=======
<<ok>>
+++++++ REPLACE
""",
            "<<ok>>\n",
        ),
        (
            "```js\nconsole.log('x')\n```\n",
            """------- SEARCH
```js
console.log('x')
```
=======
```ts
console.log('y')
```
+++++++ REPLACE
""",
            "```ts\nconsole.log('y')\n```\n",
        ),
        (
            "<node attr=\"1\">\n</node>\n",
            """------- SEARCH
<node attr=\"1\">
</node>
=======
<node attr=\"2\"/>
+++++++ REPLACE
""",
            "<node attr=\"2\"/>\n",
        ),
        (
            "edge",
            """------- SEARCH
edge
=======
EDGE
+++++++ REPLACE
""",
            "EDGE",
        ),
    ],
)
async def test_replace_in_file_applies_various_blocks(tmp_path: Path, monkeypatch, initial: str, diff_text: str, expected: str):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "e.txt"
    f.write_text(initial, encoding="utf-8")
    t = ReplaceInFileTool()
    res = await t.arun({"path": str(f), "diff": diff_text})
    assert res["type"] == "replace_file_result"
    assert f.read_text(encoding="utf-8") == expected


async def test_replace_in_file_marker_with_angle_brackets(tmp_path: Path, monkeypatch):
    """Test marker format with <<<<<<< SEARCH / ======= / +++++++ REPLACE"""
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "angle.txt"
    f.write_text("hello world", encoding="utf-8")
    t = ReplaceInFileTool()
    
    # Test with angle brackets format (<<<<<<< instead of -------)
    res = await _run(
        t, path=str(f), diff="""<<<<<<< SEARCH
hello world
=======
goodbye world
+++++++ REPLACE
"""
    )
    assert res["type"] == "replace_file_result"
    # We now support <<<<<<< format too!
    assert f.read_text(encoding="utf-8") == "goodbye world"


async def test_replace_in_file_no_separator_format(tmp_path: Path, monkeypatch):
    """Test marker format without ======= separator (like LLM sometimes sends)"""
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "nosep.txt"
    f.write_text("hello world\ngoodbye moon", encoding="utf-8")
    t = ReplaceInFileTool()
    
    # Test format without ======= separator
    res = await _run(
        t, path=str(f), diff="""------- SEARCH
hello world
goodbye moon
+++++++ REPLACE
hello universe
goodbye sun
"""
    )
    assert res["type"] == "replace_file_result"
    assert f.read_text(encoding="utf-8") == "hello universe\ngoodbye sun"


async def test_replace_in_file_apply_patch_style(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "p.txt"
    f.write_text("line1\nline2\n", encoding="utf-8")
    patch = f"""*** Begin Patch
*** Update File: {f.resolve()}
@@ -1,2 +1,2 @@
 line1
-line2
+LINE2
*** End Patch
"""
    t = ReplaceInFileTool()
    res = await t.arun({"path": str(f), "diff": patch})
    assert res["type"] == "replace_file_result"
    assert f.read_text(encoding="utf-8").splitlines() == ["line1", "LINE2"]
