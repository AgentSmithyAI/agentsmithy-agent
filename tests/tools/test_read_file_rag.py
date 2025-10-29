"""Tests for read_file tool with RAG indexing integration."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agentsmithy.tools.builtin.read_file import ReadFileTool


@pytest.mark.asyncio
async def test_read_file_indexes_in_rag(temp_project, mock_embeddings):
    """Test that reading a file automatically indexes it in RAG."""
    # Create a test file
    test_file = temp_project.root / "test_module.py"
    test_content = """def calculate_sum(a, b):
    '''Calculate sum of two numbers.'''
    return a + b

def calculate_product(a, b):
    '''Calculate product of two numbers.'''
    return a * b
"""
    test_file.write_text(test_content)

    # Create read_file tool with project context
    tool = ReadFileTool()
    tool._project = temp_project
    tool._project_root = str(temp_project.root)

    # Read the file
    result = await tool._arun(path="test_module.py")

    # Should return success
    assert result["type"] == "read_file_result"
    assert result["content"] == test_content

    # Give async task time to index
    await asyncio.sleep(0.5)

    # Check if file was indexed in RAG
    vector_store = temp_project.get_vector_store()
    has_file = await vector_store.has_file("test_module.py")

    assert has_file


@pytest.mark.asyncio
async def test_read_file_rag_indexing_fails_gracefully(temp_project):
    """Test that read_file succeeds even if RAG indexing fails."""
    # Create a test file
    test_file = temp_project.root / "test.txt"
    test_file.write_text("Simple content")

    # Create tool without project context (RAG indexing should fail silently)
    tool = ReadFileTool()
    tool._project_root = str(temp_project.root)
    # Intentionally don't set _project

    # Read should still work
    result = await tool._arun(path="test.txt")

    assert result["type"] == "read_file_result"
    assert result["content"] == "Simple content"


@pytest.mark.asyncio
async def test_read_file_indexes_relative_path(temp_project, mock_embeddings):
    """Test that files are indexed with relative paths."""
    # Create nested directory structure
    subdir = temp_project.root / "src" / "utils"
    subdir.mkdir(parents=True)

    test_file = subdir / "helpers.py"
    test_file.write_text("def helper():\n    pass")

    # Read with relative path
    tool = ReadFileTool()
    tool._project = temp_project
    tool._project_root = str(temp_project.root)

    result = await tool._arun(path="src/utils/helpers.py")

    assert result["type"] == "read_file_result"

    # Give async task time to index
    await asyncio.sleep(0.5)

    # Should be indexed with relative path
    vector_store = temp_project.get_vector_store()
    assert await vector_store.has_file("src/utils/helpers.py")


@pytest.mark.asyncio
async def test_read_file_updates_rag_on_reread(temp_project, mock_embeddings):
    """Test that re-reading a modified file updates RAG."""
    # Create initial file
    test_file = temp_project.root / "changeable.py"
    test_file.write_text("version = 1")

    tool = ReadFileTool()
    tool._project = temp_project
    tool._project_root = str(temp_project.root)

    # Read first version
    result1 = await tool._arun(path="changeable.py")
    assert "version = 1" in result1["content"]

    await asyncio.sleep(0.5)

    # Modify file
    test_file.write_text("version = 2\nnew_feature = True")

    # Read again
    result2 = await tool._arun(path="changeable.py")
    assert "version = 2" in result2["content"]

    await asyncio.sleep(0.5)

    # RAG should have updated content
    vector_store = temp_project.get_vector_store()
    results = await vector_store.similarity_search("new_feature", k=1)

    assert len(results) > 0
    assert "new_feature" in results[0].page_content


@pytest.mark.asyncio
async def test_read_file_outside_project_root(temp_project, mock_embeddings):
    """Test reading file outside project root still works."""
    # Create a file outside project root
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("External file content")
        external_file = Path(f.name)

    try:
        tool = ReadFileTool()
        tool._project = temp_project
        tool._project_root = str(temp_project.root)

        # Read with absolute path
        result = await tool._arun(path=str(external_file))

        assert result["type"] == "read_file_result"
        assert result["content"] == "External file content"

        await asyncio.sleep(0.5)

        # Note: Files outside project root use absolute paths in RAG
        # We don't check has_file here because the behavior may vary
        # based on whether the file path is normalized or not

    finally:
        external_file.unlink()


@pytest.mark.asyncio
async def test_read_file_large_content_chunking(temp_project, mock_embeddings):
    """Test that large files are properly chunked in RAG."""
    # Create a large file
    large_content = "\n".join([f"Line {i}: Some content here" for i in range(100)])
    test_file = temp_project.root / "large.py"
    test_file.write_text(large_content)

    tool = ReadFileTool()
    tool._project = temp_project
    tool._project_root = str(temp_project.root)

    result = await tool._arun(path="large.py")
    assert result["type"] == "read_file_result"

    await asyncio.sleep(0.5)

    # Should be indexed
    vector_store = temp_project.get_vector_store()
    assert await vector_store.has_file("large.py")

    # Should be searchable
    results = await vector_store.similarity_search("Line 50", k=2)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_read_file_binary_not_indexed(temp_project):
    """Test that binary files that fail to read are not indexed."""
    # Create a binary file
    binary_file = temp_project.root / "image.bin"
    binary_file.write_bytes(b"\x00\x01\x02\xff\xfe")

    tool = ReadFileTool()
    tool._project = temp_project
    tool._project_root = str(temp_project.root)

    # Reading binary should fail with decode error
    result = await tool._arun(path="image.bin")

    assert result["type"] == "tool_error"
    assert result["code"] == "decode_error"

    await asyncio.sleep(0.5)

    # Should not be in RAG
    vector_store = temp_project.get_vector_store()
    assert not await vector_store.has_file("image.bin")
