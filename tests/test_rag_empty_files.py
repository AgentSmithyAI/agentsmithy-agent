"""Tests for handling empty files in RAG system."""

import pytest

from agentsmithy.rag.vector_store import VectorStoreManager


@pytest.mark.asyncio
async def test_index_empty_file(temp_project, mock_embeddings):
    """Test that indexing an empty file doesn't raise an error."""
    # Create an empty file
    empty_file = temp_project.root / "empty.txt"
    empty_file.write_text("")

    vector_store = VectorStoreManager(temp_project)

    # Should not raise an error, returns empty list
    ids = await vector_store.index_file("empty.txt", "")

    assert ids == []


@pytest.mark.asyncio
async def test_index_empty_file_from_disk(temp_project, mock_embeddings):
    """Test indexing an empty file by reading from disk."""
    # Create an empty file
    empty_file = temp_project.root / "empty.py"
    empty_file.write_text("")

    vector_store = VectorStoreManager(temp_project)

    # Index without providing content (will read from disk)
    ids = await vector_store.index_file("empty.py")

    assert ids == []


@pytest.mark.asyncio
async def test_empty_file_not_in_index(temp_project, mock_embeddings):
    """Test that empty files don't create entries in the index."""
    # Create and index an empty file
    empty_file = temp_project.root / "empty.txt"
    empty_file.write_text("")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("empty.txt", "")

    # Empty files shouldn't be in the index (no chunks created)
    indexed = vector_store.get_indexed_files()
    assert "empty.txt" not in indexed


@pytest.mark.asyncio
async def test_search_with_empty_file_indexed(temp_project, mock_embeddings):
    """Test that searching works even if empty files were indexed."""
    vector_store = VectorStoreManager(temp_project)

    # Index an empty file
    empty_file = temp_project.root / "empty.txt"
    empty_file.write_text("")
    await vector_store.index_file("empty.txt", "")

    # Index a file with content
    content_file = temp_project.root / "content.txt"
    content_file.write_text("This file has actual content")
    await vector_store.index_file("content.txt", content_file.read_text())

    # Search should work and return results from non-empty file
    results = await vector_store.similarity_search("content", k=5)

    assert len(results) > 0
    assert all("empty.txt" not in r.metadata.get("source", "") for r in results)


@pytest.mark.asyncio
async def test_file_becomes_empty_after_modification(temp_project, mock_embeddings):
    """Test that a file that becomes empty is handled correctly."""
    test_file = temp_project.root / "becomes_empty.txt"
    test_file.write_text("Original content with text")

    vector_store = VectorStoreManager(temp_project)

    # Index with content
    await vector_store.index_file("becomes_empty.txt", test_file.read_text())

    # Verify it's indexed
    indexed = vector_store.get_indexed_files()
    assert "becomes_empty.txt" in indexed

    # Make file empty
    test_file.write_text("")

    # Reindex
    ids = await vector_store.index_file("becomes_empty.txt", "")

    assert ids == []

    # Should be removed from index (no chunks)
    indexed = vector_store.get_indexed_files()
    assert "becomes_empty.txt" not in indexed


@pytest.mark.asyncio
async def test_sync_detects_file_became_empty(temp_project, mock_embeddings):
    """Test that sync detects when a file becomes empty."""
    test_file = temp_project.root / "will_be_emptied.txt"
    test_file.write_text("Some initial content here")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("will_be_emptied.txt", test_file.read_text())

    # Verify it's indexed
    assert await vector_store.has_file("will_be_emptied.txt")

    # Empty the file
    test_file.write_text("")

    # Sync should detect the change
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 1
    # File was reindexed (though now with empty content)
    # Empty files result in no chunks, effectively removing from index
    indexed = vector_store.get_indexed_files()
    assert "will_be_emptied.txt" not in indexed


@pytest.mark.asyncio
async def test_empty_file_with_whitespace_only(temp_project, mock_embeddings):
    """Test that files with only whitespace are handled correctly."""
    # Files with only whitespace/newlines should also produce no chunks
    whitespace_file = temp_project.root / "whitespace.txt"
    whitespace_file.write_text("   \n\n  \t  \n")

    vector_store = VectorStoreManager(temp_project)

    # Should not raise an error
    ids = await vector_store.index_file("whitespace.txt", whitespace_file.read_text())

    # Whitespace-only files may or may not create chunks depending on splitter
    # Just verify no error is raised
    assert isinstance(ids, list)


@pytest.mark.asyncio
async def test_multiple_empty_files(temp_project, mock_embeddings):
    """Test indexing multiple empty files in sequence."""
    vector_store = VectorStoreManager(temp_project)

    # Create and index multiple empty files
    for i in range(5):
        empty_file = temp_project.root / f"empty_{i}.txt"
        empty_file.write_text("")
        ids = await vector_store.index_file(f"empty_{i}.txt", "")
        assert ids == []

    # None should be in the index
    indexed = vector_store.get_indexed_files()
    assert all(f"empty_{i}.txt" not in indexed for i in range(5))


@pytest.mark.asyncio
async def test_mixed_empty_and_nonempty_files(temp_project, mock_embeddings):
    """Test indexing a mix of empty and non-empty files."""
    vector_store = VectorStoreManager(temp_project)

    # Create files
    empty1 = temp_project.root / "empty1.txt"
    empty1.write_text("")

    content1 = temp_project.root / "content1.txt"
    content1.write_text("First file with content")

    empty2 = temp_project.root / "empty2.txt"
    empty2.write_text("")

    content2 = temp_project.root / "content2.txt"
    content2.write_text("Second file with content")

    # Index all
    await vector_store.index_file("empty1.txt", "")
    await vector_store.index_file("content1.txt", content1.read_text())
    await vector_store.index_file("empty2.txt", "")
    await vector_store.index_file("content2.txt", content2.read_text())

    # Only files with content should be indexed
    indexed = vector_store.get_indexed_files()
    assert "empty1.txt" not in indexed
    assert "empty2.txt" not in indexed
    assert "content1.txt" in indexed
    assert "content2.txt" in indexed
    assert len(indexed) == 2


@pytest.mark.asyncio
async def test_has_file_returns_false_for_empty(temp_project, mock_embeddings):
    """Test that has_file returns False for indexed empty files."""
    empty_file = temp_project.root / "empty.txt"
    empty_file.write_text("")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("empty.txt", "")

    # Empty files have no chunks, so has_file should return False
    assert not await vector_store.has_file("empty.txt")


@pytest.mark.asyncio
async def test_reindex_empty_file(temp_project, mock_embeddings):
    """Test reindexing an empty file."""
    empty_file = temp_project.root / "empty.txt"
    empty_file.write_text("")

    vector_store = VectorStoreManager(temp_project)

    # Initial index
    await vector_store.index_file("empty.txt", "")

    # Reindex
    ids = await vector_store.reindex_file("empty.txt")

    assert ids == []
    assert not await vector_store.has_file("empty.txt")
