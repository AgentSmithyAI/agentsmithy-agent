from __future__ import annotations

from pathlib import Path

import pytest

from agentsmithy_server.tools.builtin.list_files import ListFilesTool

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


async def test_list_files_with_ignored_directories(tmp_path: Path):
    """Test that default ignored directories are excluded."""
    # Create regular directories
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Readme")

    # Create ignored directories
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.json").write_text("{}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test.pyc").write_text("compiled")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("gitconfig")

    t = ListFilesTool()
    res = await _run(t, path=str(tmp_path), recursive=True)
    items = res["items"]

    # Check that regular files are included
    assert any("src/main.py" in p for p in items)
    assert any("docs/readme.md" in p for p in items)

    # Check that ignored directories are excluded
    assert not any("node_modules" in p for p in items)
    assert not any("__pycache__" in p for p in items)
    assert not any(".git" in p for p in items)


async def test_list_files_restricted_paths(tmp_path: Path):
    """Test that restricted paths are blocked."""
    t = ListFilesTool()

    # Test root directory access
    res = await _run(t, path="/")
    assert res["type"] == "list_files_error"
    assert "restricted" in res["error"].lower()

    # Test home directory access
    res = await _run(t, path=str(Path.home()))
    assert res["type"] == "list_files_error"
    assert "restricted" in res["error"].lower()

    # Test normal directory access
    res = await _run(t, path=str(tmp_path))
    assert res["type"] == "list_files_result"


async def test_list_files_nonexistent_path(tmp_path: Path):
    """Test error handling for non-existent paths."""
    t = ListFilesTool()
    res = await _run(t, path=str(tmp_path / "nonexistent"))

    assert res["type"] == "list_files_error"
    assert res["error_type"] == "PathNotFoundError"
    assert "does not exist" in res["error"]


async def test_list_files_file_instead_of_directory(tmp_path: Path):
    """Test error handling when path is a file instead of directory."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("content")

    t = ListFilesTool()
    res = await _run(t, path=str(file_path))

    assert res["type"] == "list_files_error"
    assert res["error_type"] == "NotADirectoryError"
    assert "not a directory" in res["error"]
