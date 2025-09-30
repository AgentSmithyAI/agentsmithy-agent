from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.builtin.search_files import SearchFilesTool

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


async def test_search_files_with_ignored_directories(tmp_path: Path):
    """Test that search excludes default ignored directories."""
    # Create regular files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "TODO: implement feature", encoding="utf-8"
    )

    # Create files in ignored directories
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("TODO: fix bug", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test.py").write_text("TODO: cleanup", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hooks.py").write_text("TODO: git hook", encoding="utf-8")

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"TODO:", file_pattern="**/*")
    results = res["results"]

    # Should only find TODO in src/main.py
    assert len(results) == 1
    assert "src/main.py" in results[0]["file"]
    assert "implement feature" in results[0]["context"]


async def test_search_files_hidden_files_handling(tmp_path: Path):
    """Test that hidden files are excluded by default."""
    # Create regular and hidden files
    (tmp_path / "visible.txt").write_text("FIND ME", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("FIND ME", encoding="utf-8")
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "settings.json").write_text("FIND ME", encoding="utf-8")

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"FIND ME", file_pattern="**/*")
    results = res["results"]

    # Should only find in visible file
    assert len(results) == 1
    assert "visible.txt" in results[0]["file"]

    # Test with explicit hidden file pattern
    res2 = await _run(t, path=str(tmp_path), regex=r"FIND ME", file_pattern=".*")
    results2 = res2["results"]
    # Should find hidden files when explicitly requested
    assert len(results2) >= 1


async def test_search_files_returns_all_results(tmp_path: Path):
    """Test that search returns all matching results without limits."""
    # Create many files with matches
    num_files = 500
    for i in range(num_files):
        (tmp_path / f"file{i}.txt").write_text(f"MATCH {i}", encoding="utf-8")

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"MATCH", file_pattern="**/*.txt")
    results = res["results"]

    # Should return all results
    assert len(results) == num_files
    assert res.get("truncated") is None
    assert "truncated" not in str(res)


async def test_search_files_restricted_paths(tmp_path: Path):
    """Test that restricted paths are blocked."""
    t = SearchFilesTool()

    # Test root directory
    res = await _run(t, path="/", regex=r"test", file_pattern="**/*")
    assert res["type"] in {"search_files_error", "tool_error"}
    assert "restricted" in res["error"].lower()

    # Test home directory
    res = await _run(t, path=str(Path.home()), regex=r"test", file_pattern="**/*")
    assert res["type"] in {"search_files_error", "tool_error"}
    assert "restricted" in res["error"].lower()


async def test_search_files_invalid_regex(tmp_path: Path):
    """Test error handling for invalid regex patterns."""
    (tmp_path / "test.txt").write_text("content", encoding="utf-8")

    t = SearchFilesTool()
    res = await _run(t, path=str(tmp_path), regex=r"[unclosed", file_pattern="**/*.txt")

    assert res["type"] in {"search_files_error", "tool_error"}
    assert res["error_type"] == "RegexError"
    assert "Invalid regex" in res["error"]


async def test_search_files_nonexistent_path(tmp_path: Path):
    """Test error handling for non-existent paths."""
    t = SearchFilesTool()
    res = await _run(
        t, path=str(tmp_path / "nonexistent"), regex=r"test", file_pattern="**/*"
    )

    assert res["type"] in {"search_files_error", "tool_error"}
    assert res["error_type"] == "PathNotFoundError"
    assert "does not exist" in res["error"]
