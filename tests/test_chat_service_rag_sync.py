"""Tests for RAG synchronization before processing user messages.

Tests verify that RAG is synced before each user message to catch external changes.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Mock embeddings to avoid OpenAI API calls."""
    mock_embed = MagicMock()

    # Mock sync methods - return one vector per input text
    def fake_embed_documents(texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5] for _ in texts]

    mock_embed.embed_documents.side_effect = fake_embed_documents
    mock_embed.embed_query.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

    # Mock async methods
    async def fake_aembed_documents(texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5] for _ in texts]

    mock_embed.aembed_documents = AsyncMock(side_effect=fake_aembed_documents)
    mock_embed.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])

    monkeypatch.setattr(
        "agentsmithy.rag.embeddings.EmbeddingsManager.embeddings",
        property(lambda self: mock_embed),
    )
    return mock_embed


@pytest.mark.asyncio
async def test_sync_detects_external_file_changes(temp_project, mock_embeddings):
    """Test that sync detects and reindexes externally modified files.

    This simulates changes made via run_command or manual edits.
    """
    # Index a file in RAG
    test_file = temp_project.root / "external_change.py"
    test_file.write_text("version = 1")

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("external_change.py", test_file.read_text())

    # Verify it's indexed
    assert await vector_store.has_file("external_change.py")
    indexed = vector_store.get_indexed_files()
    original_hash = indexed["external_change.py"]

    # Simulate external modification (e.g., run_command or manual edit)
    test_file.write_text("version = 2  # changed externally!")

    # Calculate new hash
    import hashlib

    new_hash = hashlib.md5(test_file.read_text().encode("utf-8")).hexdigest()
    assert new_hash != original_hash  # Hash should differ

    # Sync RAG (this is what chat_service does before processing)
    stats = await vector_store.sync_files_if_needed()

    # Should have reindexed the changed file
    assert stats["checked"] == 1
    assert stats["reindexed"] == 1
    assert stats["removed"] == 0

    # Verify RAG was synced and now has new hash
    indexed_after = vector_store.get_indexed_files()
    assert indexed_after["external_change.py"] == new_hash

    # Verify RAG has new content
    results = await vector_store.similarity_search("changed externally", k=1)
    assert len(results) > 0
    assert "changed externally" in results[0].page_content


@pytest.mark.asyncio
async def test_sync_catches_run_command_changes(temp_project, mock_embeddings):
    """Test that sync catches changes made via run_command."""
    # Index a file
    config_file = temp_project.root / "config.json"
    config_file.write_text('{"debug": false}')

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("config.json", config_file.read_text())

    # Verify original content in RAG
    results = await vector_store.similarity_search("debug false", k=1)
    assert any("false" in r.page_content for r in results)

    # Simulate run_command changed the file (external to tools)
    config_file.write_text('{"debug": true, "verbose": true}')

    # Sync (this is what happens before processing)
    stats = await vector_store.sync_files_if_needed()

    assert stats["reindexed"] == 1

    # RAG should now have updated content
    results = await vector_store.similarity_search("verbose", k=1)
    assert len(results) > 0
    assert "verbose" in results[0].page_content


@pytest.mark.asyncio
async def test_sync_removes_deleted_files(temp_project, mock_embeddings):
    """Test that sync removes files that were deleted externally."""
    # Index a file
    temp_file = temp_project.root / "temp.txt"
    temp_file.write_text("temporary content")

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("temp.txt", temp_file.read_text())

    assert await vector_store.has_file("temp.txt")

    # Delete file externally (not via delete_file tool)
    temp_file.unlink()

    # Sync
    stats = await vector_store.sync_files_if_needed()

    assert stats["removed"] == 1

    # RAG should have removed the file
    assert not await vector_store.has_file("temp.txt")


@pytest.mark.asyncio
async def test_sync_preserves_unchanged(temp_project, mock_embeddings):
    """Test that sync doesn't reindex files that haven't changed."""
    # Index a file
    stable_file = temp_project.root / "stable.py"
    stable_file.write_text("stable content")

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("stable.py", stable_file.read_text())

    # Get original hash
    indexed_before = vector_store.get_indexed_files()
    hash_before = indexed_before["stable.py"]

    # Sync (should check but not reindex)
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 1
    assert stats["reindexed"] == 0

    # Hash should remain the same (not reindexed)
    indexed_after = vector_store.get_indexed_files()
    assert indexed_after["stable.py"] == hash_before


@pytest.mark.asyncio
async def test_sync_handles_multiple_file_states(temp_project, mock_embeddings):
    """Test sync with multiple files in different states (unchanged, modified, deleted)."""
    vector_store = temp_project.get_vector_store()

    # Create and index three files
    unchanged = temp_project.root / "unchanged.py"
    modified = temp_project.root / "modified.py"
    deleted = temp_project.root / "deleted.py"

    unchanged.write_text("unchanged")
    modified.write_text("old")
    deleted.write_text("will be deleted")

    await vector_store.index_file("unchanged.py", unchanged.read_text())
    await vector_store.index_file("modified.py", modified.read_text())
    await vector_store.index_file("deleted.py", deleted.read_text())

    # Modify externally
    modified.write_text("new content")
    deleted.unlink()

    # Sync
    stats = await vector_store.sync_files_if_needed()

    assert stats["checked"] == 3
    assert stats["reindexed"] == 1  # modified.py
    assert stats["removed"] == 1  # deleted.py

    # Verify:
    # 1. Unchanged still there
    assert await vector_store.has_file("unchanged.py")

    # 2. Modified has new content
    results = await vector_store.similarity_search("new content", k=1)
    assert any("new content" in r.page_content for r in results)

    # 3. Deleted is gone
    assert not await vector_store.has_file("deleted.py")
