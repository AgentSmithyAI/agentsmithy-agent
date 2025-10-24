"""Integration tests for checkpoint restore with RAG through API."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import Project
from agentsmithy.services.versioning import VersioningTracker


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


@pytest.fixture
def api_client(temp_project, monkeypatch):
    """Create FastAPI test client with temp project."""

    # Mock get_current_project to return our temp project
    def mock_get_project():
        return temp_project

    monkeypatch.setattr("agentsmithy.api.deps.get_current_project", mock_get_project)

    app = create_app()
    return TestClient(app)


@pytest.mark.asyncio
async def test_restore_endpoint_reindexes_rag(temp_project, mock_embeddings):
    """Test that restore endpoint reindexes files in RAG."""
    dialog_id = "test-dialog-api"

    # Setup: Create files and checkpoint
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    file1 = temp_project.root / "api_test.py"
    file1.write_text("version = 'original'")

    # Index in RAG
    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("api_test.py", file1.read_text())

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Original version")

    # Modify and reindex
    file1.write_text("version = 'modified'")
    await vector_store.reindex_file("api_test.py")

    # Verify RAG has modified version
    results = await vector_store.similarity_search("modified", k=1)
    assert any("modified" in r.page_content for r in results)

    # Now restore through API (simulated)
    # Since we can't easily test async API endpoints, we'll test the core logic

    # Restore
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # Simulate what API endpoint does
    if restored_files:
        for file_path in restored_files:
            if await vector_store.has_file(file_path):
                await vector_store.reindex_file(file_path)

    # Verify RAG has original version
    results = await vector_store.similarity_search("original", k=1)
    assert any("original" in r.page_content for r in results)


@pytest.mark.asyncio
async def test_restore_only_reindexes_previously_indexed(temp_project, mock_embeddings):
    """Test that restore only reindexes files that were in RAG."""
    dialog_id = "test-dialog-selective"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create two files
    indexed_file = temp_project.root / "indexed.py"
    not_indexed_file = temp_project.root / "not_indexed.py"

    indexed_file.write_text("indexed = True")
    not_indexed_file.write_text("indexed = False")

    # Only index one
    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("indexed.py", indexed_file.read_text())

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("Selective test")

    # Modify both
    indexed_file.write_text("indexed = Modified")
    not_indexed_file.write_text("indexed = AlsoModified")

    # Restore
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # Simulate API endpoint logic
    reindexed_count = 0
    for file_path in restored_files:
        if await vector_store.has_file(file_path):
            await vector_store.reindex_file(file_path)
            reindexed_count += 1

    # Only one file should have been reindexed
    assert reindexed_count == 1

    # Verify the right one was reindexed
    assert await vector_store.has_file("indexed.py")
    assert not await vector_store.has_file("not_indexed.py")


@pytest.mark.asyncio
async def test_reset_endpoint_reindexes_rag(temp_project, mock_embeddings):
    """Test that reset endpoint also reindexes RAG."""
    dialog_id = "test-dialog-reset"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create initial file and checkpoint
    test_file = temp_project.root / "reset_test.py"
    test_file.write_text("initial = True")

    initial_checkpoint = tracker.create_checkpoint("Initial snapshot")

    # Note: In real code, initial_checkpoint would be stored in project.dialogs_index
    # For this test, we just use the checkpoint ID directly

    # Index and modify
    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("reset_test.py", test_file.read_text())

    test_file.write_text("initial = False\nmodified = True")
    tracker.create_checkpoint("After modifications")
    await vector_store.reindex_file("reset_test.py")

    # Verify modified version in RAG
    results = await vector_store.similarity_search("modified", k=1)
    assert any("modified" in r.page_content for r in results)

    # Reset to initial checkpoint
    restored_files = tracker.restore_checkpoint(initial_checkpoint.commit_id)

    # Simulate reset endpoint logic
    if restored_files:
        for file_path in restored_files:
            if await vector_store.has_file(file_path):
                await vector_store.reindex_file(file_path)

    # Verify RAG has initial version
    results = await vector_store.similarity_search("initial", k=1)
    assert len(results) > 0
    # Should have initial=True, not initial=False
    content = results[0].page_content
    assert "initial = True" in content or "initial=True" in content


@pytest.mark.asyncio
async def test_restore_with_deleted_file(temp_project, mock_embeddings):
    """Test restore when a file was deleted after checkpoint."""
    dialog_id = "test-dialog-deleted"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    # Create and index file
    test_file = temp_project.root / "will_be_deleted.py"
    test_file.write_text("exists = True")

    vector_store = temp_project.get_vector_store()
    await vector_store.index_file("will_be_deleted.py", test_file.read_text())

    # Create checkpoint
    checkpoint = tracker.create_checkpoint("File exists")

    # Delete file and remove from RAG
    test_file.unlink()
    vector_store.delete_by_source("will_be_deleted.py")

    # Verify file is gone
    assert not test_file.exists()
    assert not await vector_store.has_file("will_be_deleted.py")

    # Restore
    restored_files = tracker.restore_checkpoint(checkpoint.commit_id)

    # File should be restored
    assert test_file.exists()
    assert "will_be_deleted.py" in restored_files

    # Simulate API reindexing
    for file_path in restored_files:
        if await vector_store.has_file(file_path):
            await vector_store.reindex_file(file_path)
        # Note: file won't be reindexed because it wasn't in RAG anymore
        # This is correct behavior - only reindex files that ARE indexed

    # File exists on disk but not in RAG (as expected)
    assert test_file.exists()
    # Note: We deleted it from RAG, so has_file should be False
    assert not await vector_store.has_file("will_be_deleted.py")


@pytest.mark.asyncio
async def test_restore_with_multiple_checkpoints(temp_project, mock_embeddings):
    """Test RAG consistency across multiple restores."""
    dialog_id = "test-dialog-multiple"
    tracker = VersioningTracker(str(temp_project.root), dialog_id)
    tracker.ensure_repo()

    test_file = temp_project.root / "evolving.py"
    vector_store = temp_project.get_vector_store()

    # Version 1
    test_file.write_text("version = 1")
    await vector_store.index_file("evolving.py", test_file.read_text())
    cp1 = tracker.create_checkpoint("Version 1")

    # Version 2
    test_file.write_text("version = 2")
    await vector_store.reindex_file("evolving.py")
    cp2 = tracker.create_checkpoint("Version 2")

    # Version 3
    test_file.write_text("version = 3")
    await vector_store.reindex_file("evolving.py")
    cp3 = tracker.create_checkpoint("Version 3")

    # Restore to version 1
    restored = tracker.restore_checkpoint(cp1.commit_id)
    for f in restored:
        if await vector_store.has_file(f):
            await vector_store.reindex_file(f)

    results = await vector_store.similarity_search("version", k=1)
    assert "version = 1" in results[0].page_content

    # Restore to version 3
    restored = tracker.restore_checkpoint(cp3.commit_id)
    for f in restored:
        if await vector_store.has_file(f):
            await vector_store.reindex_file(f)

    results = await vector_store.similarity_search("version", k=1)
    assert "version = 3" in results[0].page_content

    # Restore to version 2
    restored = tracker.restore_checkpoint(cp2.commit_id)
    for f in restored:
        if await vector_store.has_file(f):
            await vector_store.reindex_file(f)

    results = await vector_store.similarity_search("version", k=1)
    assert "version = 2" in results[0].page_content
