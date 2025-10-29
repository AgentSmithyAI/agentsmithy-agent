from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy.tools.builtin.search_files import SearchFilesTool

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


# Tests for optimization features


async def test_search_files_respects_max_file_size(tmp_path: Path):
    """Test that files larger than MAX_FILE_SIZE_BYTES are skipped."""
    # Create a small file that should be searched
    small_file = tmp_path / "small.txt"
    small_file.write_text("needle in haystack\n" * 10, encoding="utf-8")

    # Create a large file (>10MB) that should be skipped
    large_file = tmp_path / "large.txt"
    # Write 11MB of data
    large_content = "x" * (11 * 1024 * 1024)
    large_file.write_text(large_content, encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"needle|x")

    # Should only find matches in small file, large file should be skipped
    assert len(result["results"]) > 0
    assert all("small.txt" in r["file"] for r in result["results"])
    assert not any("large.txt" in r["file"] for r in result["results"])


async def test_search_files_respects_max_results(tmp_path: Path):
    """Test that search stops after MAX_RESULTS matches."""
    # Create files with many matches
    for i in range(10):
        f = tmp_path / f"file_{i}.txt"
        # Each file has 200 matches
        f.write_text("match\n" * 200, encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"match")

    # Should stop at MAX_RESULTS (1000 by default)
    # We created 2000 potential matches, but should get max 1000
    assert len(result["results"]) <= 1000


async def test_search_files_respects_max_files_scanned(tmp_path: Path):
    """Test that search stops after scanning MAX_FILES_TO_SCAN files."""
    # Create many files (more than MAX_FILES_TO_SCAN = 2000)
    # But make it manageable for test - create subdirectories
    for i in range(100):
        subdir = tmp_path / f"dir_{i}"
        subdir.mkdir()
        for j in range(30):  # 100 * 30 = 3000 files total
            f = subdir / f"file_{j}.txt"
            f.write_text(f"content {i}_{j}\n", encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"content")

    # Should have scanned at most MAX_FILES_TO_SCAN files
    # Note: actual results might be less than files scanned
    # since not all files match, but should be within reasonable range
    assert len(result["results"]) > 0
    # Results should be less than total files (3000)
    assert len(result["results"]) < 3000


async def test_search_files_handles_binary_files_gracefully(tmp_path: Path):
    """Test that binary files don't crash the search."""
    # Create a text file
    text_file = tmp_path / "text.txt"
    text_file.write_text("findme\n", encoding="utf-8")

    # Create a binary file
    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")

    # Create another text file
    text_file2 = tmp_path / "text2.txt"
    text_file2.write_text("findme\n", encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"findme")

    # Should find matches in text files despite binary file presence
    assert len(result["results"]) == 2
    assert all("text" in r["file"] for r in result["results"])


async def test_search_files_efficient_with_many_directories(tmp_path: Path):
    """Test that os.scandir handles deep directory structures efficiently."""
    # Create a deep directory structure
    current = tmp_path
    for i in range(10):
        current = current / f"level_{i}"
        current.mkdir()
        # Add a file at each level
        (current / f"file_{i}.txt").write_text(
            f"target at level {i}\n", encoding="utf-8"
        )

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"target")

    # Should find all 10 files
    assert len(result["results"]) == 10


async def test_search_files_empty_files(tmp_path: Path):
    """Test that empty files are handled correctly."""
    # Create empty file
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")

    # Create file with content
    content = tmp_path / "content.txt"
    content.write_text("match\n", encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"match")

    # Should find only the match in content.txt
    assert len(result["results"]) == 1
    assert "content.txt" in result["results"][0]["file"]


async def test_search_files_single_line_files(tmp_path: Path):
    """Test context extraction for single-line files."""
    single = tmp_path / "single.txt"
    single.write_text("only one line with match", encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"match")

    assert len(result["results"]) == 1
    assert result["results"][0]["line"] == 1
    assert result["results"][0]["context"] == "only one line with match"


async def test_search_files_utf8_handling(tmp_path: Path):
    """Test that UTF-8 files with special characters are handled correctly."""
    utf8_file = tmp_path / "utf8.txt"
    utf8_file.write_text(
        "Привет мир\nこんにちは世界\nHello 🌍\nmatch here\n", encoding="utf-8"
    )

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"match")

    assert len(result["results"]) == 1
    assert "match here" in result["results"][0]["context"]
    # Context should include UTF-8 characters from surrounding lines
    assert (
        "🌍" in result["results"][0]["context"]
        or "世界" in result["results"][0]["context"]
    )


async def test_search_files_glob_pattern_with_nested_dirs(tmp_path: Path):
    """Test that glob patterns work correctly with nested directories."""
    # Create nested structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("python match\n", encoding="utf-8")
    (tmp_path / "src" / "main.txt").write_text("text match\n", encoding="utf-8")

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test.py").write_text("python match\n", encoding="utf-8")

    tool = SearchFilesTool()

    # Search only .py files
    result = await _run(
        tool, path=str(tmp_path), regex=r"match", file_pattern="**/*.py"
    )

    # Should find only .py files
    assert len(result["results"]) == 2
    assert all(r["file"].endswith(".py") for r in result["results"])


async def test_search_files_stops_at_first_limit_reached(tmp_path: Path):
    """Test that search stops when ANY limit is reached first."""
    # Create many small files
    for i in range(50):
        f = tmp_path / f"file_{i:03d}.txt"
        # Each file has 25 matches
        f.write_text("match\n" * 25, encoding="utf-8")

    tool = SearchFilesTool()
    result = await _run(tool, path=str(tmp_path), regex=r"match")

    # 50 files * 25 matches = 1250 potential matches
    # Should stop at MAX_RESULTS (1000)
    assert len(result["results"]) == 1000
