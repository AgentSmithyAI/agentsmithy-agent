"""Tests that file tools properly receive project context via set_context."""

import asyncio

import pytest

from agentsmithy.tools.builtin.delete_file import DeleteFileTool
from agentsmithy.tools.builtin.read_file import ReadFileTool
from agentsmithy.tools.builtin.replace_in_file import ReplaceInFileTool
from agentsmithy.tools.builtin.write_file import WriteFileTool


@pytest.mark.asyncio
async def test_read_file_indexes_with_set_context(temp_project, mock_embeddings):
    """Test that read_file indexes when project is set via set_context."""
    # Create file
    test_file = temp_project.root / "test.py"
    test_file.write_text("def hello(): pass")

    # Create tool and set context (like ToolExecutor does)
    tool = ReadFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_context(temp_project, "test-dialog")

    # Read file
    result = await tool._arun(path="test.py")

    assert result["type"] == "read_file_result"

    # Give async indexing time to complete
    await asyncio.sleep(0.5)

    # Verify file was indexed
    vector_store = temp_project.get_vector_store()
    assert await vector_store.has_file("test.py")


@pytest.mark.asyncio
async def test_write_file_indexes_with_set_context(temp_project, mock_embeddings):
    """Test that write_file indexes when project is set via set_context."""
    # Create tool and set context
    tool = WriteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id("test-dialog")
    tool.set_context(temp_project, "test-dialog")

    # Write file
    result = await tool._arun(path="new_file.py", content="def new(): return True")

    assert result["type"] == "write_file_result"

    # Give async indexing time to complete
    await asyncio.sleep(0.5)

    # Verify file was indexed
    vector_store = temp_project.get_vector_store()
    assert await vector_store.has_file("new_file.py")


@pytest.mark.asyncio
async def test_replace_in_file_reindexes_with_set_context(
    temp_project, mock_embeddings
):
    """Test that replace_in_file reindexes when project is set via set_context."""
    # Create initial file
    test_file = temp_project.root / "edit_me.py"
    test_file.write_text("old_value = 1")

    # Create tool and set context
    tool = ReplaceInFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id("test-dialog")
    tool.set_context(temp_project, "test-dialog")

    # Edit file
    diff = """
------- SEARCH
old_value = 1
=======
new_value = 2
+++++++ REPLACE
"""
    result = await tool._arun(path="edit_me.py", diff=diff)

    assert result["type"] == "replace_file_result"

    # Give async indexing time to complete
    await asyncio.sleep(0.5)

    # Verify file was reindexed
    vector_store = temp_project.get_vector_store()
    assert await vector_store.has_file("edit_me.py")

    # Verify new content is in RAG
    results = await vector_store.similarity_search("new_value", k=1)
    assert any("new_value" in r.page_content for r in results)


@pytest.mark.asyncio
async def test_delete_file_removes_from_rag_with_set_context(
    temp_project, mock_embeddings
):
    """Test that delete_file removes from RAG when project is set via set_context."""
    # Create and index file first
    test_file = temp_project.root / "to_delete.py"
    test_file.write_text("will be deleted")

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("to_delete.py", test_file.read_text())

    assert await vector_store.has_file("to_delete.py")

    # Create tool and set context
    tool = DeleteFileTool()
    tool.set_project_root(str(temp_project.root))
    tool.set_dialog_id("test-dialog")
    tool.set_context(temp_project, "test-dialog")

    # Delete file
    result = await tool._arun(path="to_delete.py")

    assert result["type"] == "delete_file_result"

    # Verify file was removed from RAG (sync operation, no sleep needed)
    assert not await vector_store.has_file("to_delete.py")


@pytest.mark.asyncio
async def test_tools_work_without_set_context(temp_project):
    """Test that tools still work without set_context (RAG just doesn't index)."""
    # This ensures backward compatibility - tools don't crash if set_context not called

    test_file = temp_project.root / "no_context.txt"
    test_file.write_text("original")

    # Read without set_context
    tool = ReadFileTool()
    tool.set_project_root(str(temp_project.root))
    result = await tool._arun(path="no_context.txt")

    # Should work fine
    assert result["type"] == "read_file_result"
    assert result["content"] == "original"

    # RAG indexing just silently skipped (no crash)


@pytest.mark.asyncio
async def test_set_context_called_by_tool_executor(temp_project, mock_embeddings):
    """Test that ToolExecutor properly calls set_context on file tools."""
    from unittest.mock import Mock

    from agentsmithy.llm.provider import LLMProvider
    from agentsmithy.tools.build_registry import build_registry
    from agentsmithy.tools.tool_executor import ToolExecutor

    # Create mock LLM provider
    mock_llm = Mock(spec=LLMProvider)

    # Build registry with real tools
    registry = build_registry()
    executor = ToolExecutor(registry, mock_llm)

    # Set context (this should propagate to all tools)
    executor.set_context(temp_project, "test-dialog")

    # Check that file tools received the project context
    read_tool = registry.get_tool("read_file")
    write_tool = registry.get_tool("write_to_file")
    replace_tool = registry.get_tool("replace_in_file")
    delete_tool = registry.get_tool("delete_file")

    assert hasattr(read_tool, "_project")
    assert read_tool._project == temp_project

    assert hasattr(write_tool, "_project")
    assert write_tool._project == temp_project

    assert hasattr(replace_tool, "_project")
    assert replace_tool._project == temp_project

    assert hasattr(delete_tool, "_project")
    assert delete_tool._project == temp_project
