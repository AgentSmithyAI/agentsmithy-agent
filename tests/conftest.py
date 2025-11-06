"""Shared pytest fixtures for all tests."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentsmithy.core.project import Project


@pytest.fixture(autouse=True)
def cleanup_background_tasks():
    """Clean up background tasks after each test to prevent resource warnings.

    This prevents warnings about unawaited coroutines when tests use
    TestClient (sync) which closes event loop before background tasks start.
    """
    yield

    # Clean up any background tasks that were created during the test
    # Cancel any pending tasks to prevent "coroutine was never awaited" warnings
    try:
        from agentsmithy.core.background_tasks import _background_manager

        if _background_manager is not None and _background_manager._tasks:
            # Cancel all pending tasks
            for task in list(_background_manager._tasks):
                if not task.done():
                    task.cancel()
            _background_manager._tasks.clear()
    except Exception:
        # If background_manager doesn't exist or cleanup fails, ignore
        pass


@pytest.fixture
def temp_project():
    """Create a temporary project for testing.

    This fixture is available to all tests in this directory and subdirectories.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        state_dir = project_root / ".agentsmithy"
        project = Project(name="test", root=project_root, state_dir=state_dir)
        project.ensure_state_dir()
        yield project


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Mock embeddings to avoid OpenAI API calls in RAG tests.

    Returns one embedding vector per input text to support chunked files.
    """
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
