"""Tests for RAG integration with checkpoint restore functionality."""

import pytest

from agentsmithy.rag.vector_store import VectorStoreManager
from agentsmithy.services.versioning import VersioningTracker


@pytest.mark.asyncio
async def test_vector_store_index_file(temp_project, mock_embeddings):
    """Test indexing a single file in vector store."""
    # Create a test file
    test_file = temp_project.root / "test.py"
    test_file.write_text("def hello():\n    print('Hello World')")

    # Create vector store
    vector_store = VectorStoreManager(temp_project)

    # Index the file
    ids = await vector_store.index_file("test.py", test_file.read_text())

    assert len(ids) > 0
    assert await vector_store.has_file("test.py")


@pytest.mark.asyncio
async def test_vector_store_has_file(temp_project, mock_embeddings):
    """Test checking if file exists in vector store."""
    vector_store = VectorStoreManager(temp_project)

    # File not indexed yet
    assert not await vector_store.has_file("nonexistent.py")

    # Index a file
    await vector_store.index_file("test.py", "print('test')")

    # Now it exists
    assert await vector_store.has_file("test.py")


@pytest.mark.asyncio
async def test_vector_store_delete_by_source(temp_project, mock_embeddings):
    """Test deleting file from vector store."""
    vector_store = VectorStoreManager(temp_project)

    # Index a file
    await vector_store.index_file("test.py", "print('test')")
    assert await vector_store.has_file("test.py")

    # Delete it
    vector_store.delete_by_source("test.py")

    # Should be gone
    assert not await vector_store.has_file("test.py")


@pytest.mark.asyncio
async def test_vector_store_reindex_file(temp_project, mock_embeddings):
    """Test reindexing a file after modification."""
    # Create and index original file
    test_file = temp_project.root / "test.py"
    test_file.write_text("def version_1():\n    pass")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("test.py", test_file.read_text())

    # Modify the file
    test_file.write_text("def version_2():\n    return 42")

    # Reindex
    ids = await vector_store.reindex_file("test.py")

    assert len(ids) > 0
    assert await vector_store.has_file("test.py")

    # Search should return new content
    results = await vector_store.similarity_search("version_2", k=1)
    assert len(results) > 0
    assert "version_2" in results[0].page_content


@pytest.mark.asyncio
async def test_vector_store_reindex_deleted_file(temp_project, mock_embeddings):
    """Test reindexing removes file if it was deleted."""
    # Create and index file
    test_file = temp_project.root / "test.py"
    test_file.write_text("def test():\n    pass")

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("test.py", test_file.read_text())
    assert await vector_store.has_file("test.py")

    # Delete the file from disk
    test_file.unlink()

    # Reindex should remove it from vector store
    ids = await vector_store.reindex_file("test.py")

    assert len(ids) == 0
    assert not await vector_store.has_file("test.py")


def test_restore_checkpoint_returns_file_list(temp_project):
    """Test that restore_checkpoint returns list of restored files."""
    dialog_id = "test-dialog-restore"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create test files
    file1 = temp_project.root / "file1.txt"
    file2 = temp_project.root / "file2.txt"
    file1.write_text("Version 1")
    file2.write_text("Data A")

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Checkpoint with 2 files")

    # Modify files
    file1.write_text("Version 2")
    file2.write_text("Data B")

    # Restore
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # Should return list of restored files
    assert isinstance(restored_files, list)
    assert len(restored_files) == 2
    assert "file1.txt" in restored_files
    assert "file2.txt" in restored_files

    # Files should be restored
    assert file1.read_text() == "Version 1"
    assert file2.read_text() == "Data A"


@pytest.mark.asyncio
async def test_restore_checkpoint_reindexes_rag(temp_project, mock_embeddings):
    """Test that restoring checkpoint reindexes files in RAG."""
    dialog_id = "test-dialog-rag"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create and index a file
    test_file = temp_project.root / "main.py"
    original_content = "def original():\n    return 'v1'"
    test_file.write_text(original_content)

    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("main.py", original_content)

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Original version")

    # Modify and reindex
    modified_content = "def modified():\n    return 'v2'"
    test_file.write_text(modified_content)
    await vector_store.reindex_file("main.py")

    # Verify RAG has modified version
    results = await vector_store.similarity_search("modified", k=1)
    assert len(results) > 0
    assert "modified" in results[0].page_content

    # Restore to checkpoint
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # Manually reindex (simulating what the API endpoint does)
    for file_path in restored_files:
        if await vector_store.has_file(file_path):
            await vector_store.reindex_file(file_path)

    # Verify RAG now has original version
    results = await vector_store.similarity_search("original", k=1)
    assert len(results) > 0
    assert "original" in results[0].page_content
    assert "modified" not in results[0].page_content


@pytest.mark.asyncio
async def test_index_file_with_content_parameter(temp_project, mock_embeddings):
    """Test indexing file with explicit content parameter."""
    vector_store = VectorStoreManager(temp_project)

    # Index without creating actual file
    content = "def test():\n    pass"
    ids = await vector_store.index_file("virtual.py", content)

    assert len(ids) > 0
    assert await vector_store.has_file("virtual.py")


@pytest.mark.asyncio
async def test_index_file_reads_from_disk(temp_project, mock_embeddings):
    """Test indexing file reads from disk when content not provided."""
    # Create file
    test_file = temp_project.root / "disk_file.py"
    test_file.write_text("def from_disk():\n    return True")

    vector_store = VectorStoreManager(temp_project)

    # Index without providing content
    ids = await vector_store.index_file("disk_file.py")

    assert len(ids) > 0
    assert await vector_store.has_file("disk_file.py")

    # Verify content was read
    results = await vector_store.similarity_search("from_disk", k=1)
    assert len(results) > 0
    assert "from_disk" in results[0].page_content


@pytest.mark.asyncio
async def test_index_file_handles_nonexistent(temp_project):
    """Test indexing nonexistent file returns empty list."""
    vector_store = VectorStoreManager(temp_project)

    # Try to index file that doesn't exist (without content)
    ids = await vector_store.index_file("nonexistent.py")

    assert len(ids) == 0


@pytest.mark.asyncio
async def test_reindex_files_batch(temp_project, mock_embeddings):
    """Test batch reindexing of multiple files."""
    vector_store = VectorStoreManager(temp_project)

    # Create and index three files
    file1 = temp_project.root / "file1.py"
    file2 = temp_project.root / "file2.py"
    file3 = temp_project.root / "file3.py"

    file1.write_text("content1")
    file2.write_text("content2")
    file3.write_text("content3")

    # Only index two of them
    await vector_store.index_file("file1.py", file1.read_text())
    await vector_store.index_file("file2.py", file2.read_text())

    # Modify all three
    file1.write_text("modified1")
    file2.write_text("modified2")
    file3.write_text("modified3")

    # Batch reindex (should only reindex indexed files)
    reindexed_count = await vector_store.reindex_files(
        ["file1.py", "file2.py", "file3.py"]
    )

    # Should have reindexed only 2 (file3 was not indexed)
    assert reindexed_count == 2

    # Verify reindexed files have new content
    assert await vector_store.has_file("file1.py")
    assert await vector_store.has_file("file2.py")
    assert not await vector_store.has_file("file3.py")


@pytest.mark.asyncio
async def test_multiple_files_selective_reindex(temp_project, mock_embeddings):
    """Test that only indexed files are reindexed on restore."""
    dialog_id = "test-dialog-selective"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create three files
    file_indexed = temp_project.root / "indexed.py"
    file_not_indexed = temp_project.root / "not_indexed.py"
    file_indexed.write_text("indexed = True")
    file_not_indexed.write_text("indexed = False")

    # Index only one file
    vector_store = VectorStoreManager(temp_project)
    await vector_store.index_file("indexed.py", file_indexed.read_text())

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Selective test")

    # Modify both files
    file_indexed.write_text("indexed = Modified")
    file_not_indexed.write_text("indexed = AlsoModified")

    # Restore
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # Should restore both files
    assert "indexed.py" in restored_files
    assert "not_indexed.py" in restored_files

    # But only indexed.py should have been indexed in RAG
    assert await vector_store.has_file("indexed.py")
    assert not await vector_store.has_file("not_indexed.py")
