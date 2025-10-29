"""Tests for RAG mtime/size optimization.

Verifies that:
1. File metadata (mtime, size) is stored when indexing
2. Files with unchanged mtime/size are skipped during sync
3. Files with changed mtime/size are re-read and reindexed
4. Optimization significantly reduces file reads
"""

import tempfile
import time
from pathlib import Path

import pytest

from agentsmithy.core.project import Project


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        state_dir = project_root / ".agentsmithy"
        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()
        yield project


@pytest.mark.asyncio
async def test_index_file_stores_mtime_and_size(temp_project, mock_embeddings):
    """Test that indexing stores mtime and size in metadata."""
    vector_store = temp_project.get_vector_store()

    # Create and index file
    test_file = temp_project.root / "test.py"
    test_file.write_text("# test content")

    await vector_store.index_file("test.py")

    # Get metadata
    metadata = vector_store.get_file_metadata("test.py")

    assert metadata is not None
    assert "hash" in metadata
    assert "size" in metadata
    assert "mtime" in metadata
    assert metadata["size"] == len(b"# test content")
    assert metadata["mtime"] > 0


@pytest.mark.asyncio
async def test_sync_skips_unchanged_files_by_mtime(temp_project, mock_embeddings):
    """Test that sync skips files with unchanged mtime and size."""
    vector_store = temp_project.get_vector_store()

    # Create and index file
    test_file = temp_project.root / "stable.py"
    test_file.write_text("# stable content")

    await vector_store.index_file("stable.py")

    # First sync - file unchanged
    result = await vector_store.sync_files_if_needed()

    # File should be checked but skipped (not reindexed)
    assert result["checked"] == 1
    assert result["skipped"] == 1
    assert result["reindexed"] == 0


@pytest.mark.asyncio
async def test_sync_reindexes_when_mtime_changed(temp_project, mock_embeddings):
    """Test that sync reindexes files when mtime changes."""
    vector_store = temp_project.get_vector_store()

    # Create and index file
    test_file = temp_project.root / "changing.py"
    test_file.write_text("# original")

    await vector_store.index_file("changing.py")

    # Wait to ensure mtime changes (some filesystems have 1s granularity)
    time.sleep(1.1)

    # Modify file
    test_file.write_text("# modified")

    # Sync should detect change
    result = await vector_store.sync_files_if_needed()

    assert result["checked"] == 1
    assert result["reindexed"] == 1
    assert result["skipped"] == 0


@pytest.mark.asyncio
async def test_sync_reindexes_when_size_changed(temp_project, mock_embeddings):
    """Test that sync reindexes files when size changes."""
    vector_store = temp_project.get_vector_store()

    # Create and index file
    test_file = temp_project.root / "resized.py"
    test_file.write_text("# short")

    await vector_store.index_file("resized.py")

    # Change content to different size
    test_file.write_text("# much longer content here")

    # Sync should detect size change
    result = await vector_store.sync_files_if_needed()

    assert result["checked"] == 1
    assert result["reindexed"] == 1


@pytest.mark.asyncio
async def test_sync_optimization_with_many_files(temp_project, mock_embeddings):
    """Test that optimization works with many files."""
    vector_store = temp_project.get_vector_store()

    # Index 50 files
    for i in range(50):
        test_file = temp_project.root / f"file{i}.py"
        test_file.write_text(f"# content {i}")
        await vector_store.index_file(f"file{i}.py")

    # Change only 2 files
    time.sleep(0.01)
    (temp_project.root / "file5.py").write_text("# modified 5")
    (temp_project.root / "file25.py").write_text("# modified 25")

    # Sync should skip 48, reindex 2
    result = await vector_store.sync_files_if_needed()

    assert result["checked"] == 50
    assert result["skipped"] == 48  # Optimization working!
    assert result["reindexed"] == 2


@pytest.mark.asyncio
async def test_sync_handles_missing_metadata_gracefully(temp_project, mock_embeddings):
    """Test that sync works even if metadata is missing."""
    vector_store = temp_project.get_vector_store()

    # Create file without mtime/size metadata (simulate old indexed file)
    test_file = temp_project.root / "old_format.py"
    test_file.write_text("# old format")

    # Manually index with minimal metadata (simulate old version)
    from langchain_core.documents import Document

    doc = Document(
        page_content="# old format",
        metadata={"source": "old_format.py", "hash": "somehash"},
    )
    await vector_store.add_documents([doc])

    # Sync should still work (fallback to reading file)
    result = await vector_store.sync_files_if_needed()

    assert result["checked"] == 1
    # Should reindex because metadata incomplete
    assert result["reindexed"] == 1


@pytest.mark.asyncio
async def test_get_file_metadata_returns_none_for_unindexed(temp_project):
    """Test that get_file_metadata returns None for unindexed files."""
    vector_store = temp_project.get_vector_store()

    # File doesn't exist in index
    metadata = vector_store.get_file_metadata("nonexistent.py")

    assert metadata is None


@pytest.mark.asyncio
async def test_get_file_metadata_returns_data_for_indexed(
    temp_project, mock_embeddings
):
    """Test that get_file_metadata returns data for indexed files."""
    vector_store = temp_project.get_vector_store()

    # Index file
    test_file = temp_project.root / "indexed.py"
    test_file.write_text("# indexed")

    await vector_store.index_file("indexed.py")

    # Get metadata
    metadata = vector_store.get_file_metadata("indexed.py")

    assert metadata is not None
    assert metadata["source"] == "indexed.py"
    assert "hash" in metadata
    assert "size" in metadata
    assert "mtime" in metadata
