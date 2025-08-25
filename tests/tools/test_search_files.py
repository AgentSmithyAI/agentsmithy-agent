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
    f.write_text(
        """
line1
needle here
line3
line4
""".strip(),
        encoding="utf-8",
    )

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex="needle", file_pattern="**/*.py")
    results = res["results"]
    assert len(results) == 1
    assert results[0]["file"].endswith("main.py")
    assert "needle here" in results[0]["context"]


async def test_anchor_matching_per_line(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text(
        """
start here
middle
end here
""".strip(),
        encoding="utf-8",
    )
    t = SearchFilesTool()

    res1 = await _run(t, path=str(tmp_path), regex=r"^start", file_pattern="**/*.txt")
    assert len(res1["results"]) == 1
    assert res1["results"][0]["line"] == 1

    res2 = await _run(t, path=str(tmp_path), regex=r"here$", file_pattern="**/*.txt")
    assert len(res2["results"]) == 2


async def test_lookaround_and_word_boundaries(tmp_path: Path):
    f = tmp_path / "b.txt"
    f.write_text(
        """
foobar
foo bar
xx foobar yy
""".strip(),
        encoding="utf-8",
    )
    t = SearchFilesTool()

    res1 = await _run(
        t, path=str(tmp_path), regex=r"(?<=foo)bar", file_pattern="**/*.txt"
    )
    assert len(res1["results"]) == 2

    res2 = await _run(
        t, path=str(tmp_path), regex=r"foo(?=bar)", file_pattern="**/*.txt"
    )
    assert len(res2["results"]) == 2

    res3 = await _run(t, path=str(tmp_path), regex=r"\bfoo\b", file_pattern="**/*.txt")
    assert len(res3["results"]) == 1


async def test_special_chars_and_groups(tmp_path: Path):
    f = tmp_path / "c.txt"
    f.write_text("func(123) foo func(9) func(x)\n", encoding="utf-8")
    t = SearchFilesTool()

    res = await _run(
        t, path=str(tmp_path), regex=r"func\(\d+\)", file_pattern="**/*.txt"
    )
    assert len(res["results"]) == 1
    assert res["results"][0]["context"].count("func(") >= 2


async def test_inline_flags_case_insensitive(tmp_path: Path):
    f = tmp_path / "d.txt"
    f.write_text("TODO: fix\nDone\n", encoding="utf-8")
    t = SearchFilesTool()

    res = await _run(t, path=str(tmp_path), regex=r"(?i)todo", file_pattern="**/*.txt")
    assert len(res["results"]) == 1
    assert "TODO" in res["results"][0]["context"]


async def test_dotall_does_not_cross_lines(tmp_path: Path):
    f = tmp_path / "e.txt"
    f.write_text("foo\nxxx\nbar\n", encoding="utf-8")
    t = SearchFilesTool()

    res = await _run(t, path=str(tmp_path), regex=r"foo.*bar", file_pattern="**/*.txt")
    assert res["results"] == []

    f.write_text("foo ... bar\n", encoding="utf-8")
    res2 = await _run(t, path=str(tmp_path), regex=r"foo.*bar", file_pattern="**/*.txt")
    assert len(res2["results"]) == 1


async def test_multiple_hits_and_context_window(tmp_path: Path):
    f = tmp_path / "f.txt"
    f.write_text(
        """
line0
hit1
line2
hit2
line4
""".strip(),
        encoding="utf-8",
    )
    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"hit\d", file_pattern="**/*.txt")
    assert len(res["results"]) == 2
    for r in res["results"]:
        ctx = r["context"].splitlines()
        assert 1 <= len(ctx) <= 5


async def test_file_pattern_filters(tmp_path: Path):
    (tmp_path / "g.py").write_text("magic", encoding="utf-8")
    (tmp_path / "g.txt").write_text("magic", encoding="utf-8")
    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"magic", file_pattern="**/*.py")
    assert len(res["results"]) == 1
    assert res["results"][0]["file"].endswith("g.py")


async def test_alternation_groups_and_escaping(tmp_path: Path):
    f = tmp_path / "h.txt"
    f.write_text("cat dog catalog category doge\n", encoding="utf-8")
    t = SearchFilesTool()

    # Alternation for exact words
    res1 = await _run(
        t, path=str(tmp_path), regex=r"\b(cat|dog)\b", file_pattern="**/*.txt"
    )
    # Both words appear once as whole words
    assert len(res1["results"]) == 1
    ctx1 = res1["results"][0]["context"]
    assert " cat " in f" {ctx1} " or ctx1.startswith("cat ") or ctx1.endswith(" cat")
    assert " dog " in f" {ctx1} " or ctx1.startswith("dog ") or ctx1.endswith(" dog")

    # Grouped alternation inside larger token
    res2 = await _run(
        t, path=str(tmp_path), regex=r"cat(alog|egory)", file_pattern="**/*.txt"
    )
    assert len(res2["results"]) == 1
    assert (
        "catalog" in res2["results"][0]["context"]
        or "category" in res2["results"][0]["context"]
    )

    # Escaping pipe and parentheses should not act as alternation/group
    res3 = await _run(
        t, path=str(tmp_path), regex=r"cat\|dog\(\)", file_pattern="**/*.txt"
    )
    assert res3["results"] == []
