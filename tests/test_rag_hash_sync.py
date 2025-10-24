"""Tests for hash-based RAG synchronization."""

import pytest

from agentsmithy.rag.vector_store import VectorStoreManager


@pytest.mark.asyncio
async def test_index_file_stores_hash(temp_project, mock_embeddings):
    """Test that indexing a file stores its hash in metadata."""
    # Create and index a file
    test_file = temp_project.root / "test.py"
    content = "def hello():\n    return 'world'"
    test_file.write_text(content)

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("test.py", content)

    # Get indexed files
    indexed = vector_store.get_indexed_files()

    assert "test.py" in indexed
    assert len(indexed["test.py"]) == 32  # MD5 hash length


@pytest.mark.asyncio
async def test_get_indexed_files(temp_project, mock_embeddings):
    """Test getting list of all indexed files with hashes."""
    vector_store = VectorStoreManager(temp_project)

    # Index multiple files
    file1 = temp_project.root / "file1.py"
    file2 = temp_project.root / "file2.py"

    file1.write_text("content1")
    file2.write_text("content2")

    await vector_store.index_file("file1.py", file1.read_text())
    await vector_store.index_file("file2.py", file2.read_text())

    # Get all indexed files
    indexed = vector_store.get_indexed_files()

    assert len(indexed) == 2
    assert "file1.py" in indexed
    assert "file2.py" in indexed
    assert indexed["file1.py"] != indexed["file2.py"]  # Different hashes


@pytest.mark.asyncio
async def test_sync_files_no_changes(temp_project, mock_embeddings):
    """Test sync when no files have changed."""
    # Create and index a file
    test_file = temp_project.root / "test.py"
    test_file.write_text("unchanged")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("test.py", test_file.read_text())

    # Sync - should find no changes
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 1
    assert stats["reindexed"] == 0
    assert stats["removed"] == 0


@pytest.mark.asyncio
async def test_sync_files_detects_changes(temp_project, mock_embeddings):
    """Test sync detects and reindexes changed files."""
    # Create and index a file
    test_file = temp_project.root / "test.py"
    test_file.write_text("version 1")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("test.py", test_file.read_text())

    # Modify file on disk (simulating external change)
    test_file.write_text("version 2 - modified externally")

    # Sync should detect change and reindex
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 1
    assert stats["reindexed"] == 1
    assert stats["removed"] == 0

    # Verify new content is indexed
    results = await vector_store.similarity_search("modified externally", k=1)
    assert len(results) > 0
    assert "modified externally" in results[0].page_content


@pytest.mark.asyncio
async def test_sync_files_removes_deleted(temp_project, mock_embeddings):
    """Test sync removes files that were deleted from disk."""
    # Create and index a file
    test_file = temp_project.root / "temporary.py"
    test_file.write_text("will be deleted")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("temporary.py", test_file.read_text())

    # Verify it's indexed
    assert await vector_store.has_file("temporary.py")

    # Delete file from disk
    test_file.unlink()

    # Sync should remove from RAG
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 1
    assert stats["reindexed"] == 0
    assert stats["removed"] == 1

    # Verify it's no longer indexed
    assert not await vector_store.has_file("temporary.py")


@pytest.mark.asyncio
async def test_sync_files_mixed_changes(temp_project, mock_embeddings):
    """Test sync with mix of unchanged, changed, and deleted files."""
    vector_store = VectorStoreManager(temp_project)

    # Create three files
    unchanged = temp_project.root / "unchanged.py"
    changed = temp_project.root / "changed.py"
    deleted = temp_project.root / "deleted.py"

    unchanged.write_text("stays the same")
    changed.write_text("old content")
    deleted.write_text("will be deleted")

    # Index all three
    await vector_store.index_file("unchanged.py", unchanged.read_text())
    await vector_store.index_file("changed.py", changed.read_text())
    await vector_store.index_file("deleted.py", deleted.read_text())

    # Modify one, delete one, leave one unchanged
    changed.write_text("new content")
    deleted.unlink()

    # Sync
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 3
    assert stats["reindexed"] == 1  # changed.py
    assert stats["removed"] == 1  # deleted.py


@pytest.mark.asyncio
async def test_sync_files_external_modification(temp_project, mock_embeddings):
    """Test that sync catches changes made outside of tools (e.g. via run_command)."""
    # This simulates the scenario where a file is modified by run_command
    # or manually, bypassing the automatic indexing in tools

    test_file = temp_project.root / "external.py"
    test_file.write_text("original content")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("external.py", test_file.read_text())

    # Simulate external modification (e.g., user runs 'sed' command)
    test_file.write_text("externally modified content")

    # Sync should catch this
    stats = await vector_store.sync_files_if_needed()

    assert stats["reindexed"] == 1

    # Verify RAG has new content
    indexed = vector_store.get_indexed_files()
    # Read current file and calculate its hash
    import hashlib

    current_hash = hashlib.md5(test_file.read_text().encode("utf-8")).hexdigest()
    assert indexed["external.py"] == current_hash


@pytest.mark.asyncio
async def test_sync_preserves_unchanged_files(temp_project, mock_embeddings):
    """Test that sync doesn't unnecessarily reindex unchanged files."""
    test_file = temp_project.root / "stable.py"
    test_file.write_text("stable content")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("stable.py", test_file.read_text())

    # Get original hash
    original_indexed = vector_store.get_indexed_files()
    original_hash = original_indexed["stable.py"]

    # Sync multiple times
    await vector_store.sync_files_if_needed()
    await vector_store.sync_files_if_needed()

    # Hash should remain the same (not reindexed)
    current_indexed = vector_store.get_indexed_files()
    assert current_indexed["stable.py"] == original_hash


@pytest.mark.asyncio
async def test_sync_with_empty_rag(temp_project):
    """Test sync with no indexed files."""
    vector_store = VectorStoreManager(temp_project)

    # Sync with empty RAG
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 0
    assert stats["reindexed"] == 0
    assert stats["removed"] == 0
