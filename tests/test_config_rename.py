"""Tests for POST /api/config/rename endpoint.

Tests cover:
1. Renaming workloads and updating references
2. Renaming providers and updating references
3. Error cases (not found, already exists, invalid type)
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.config import get_default_config
from agentsmithy.config.manager import ConfigManager
from agentsmithy.config.providers import LocalFileConfigProvider
from agentsmithy.config.schema import rename_entity

# =============================================================================
# Unit tests for rename_entity function
# =============================================================================


class TestRenameEntityFunction:
    """Unit tests for rename_entity helper function."""

    def test_rename_workload_basic(self):
        """Should rename workload and return empty refs if no references."""
        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {"old-workload": {"provider": "openai", "model": "gpt-4"}},
            "models": {"agents": {}, "embeddings": {}, "summarization": {}},
        }

        new_config, refs = rename_entity(
            config, "workload", "old-workload", "new-workload"
        )

        assert "old-workload" not in new_config["workloads"]
        assert "new-workload" in new_config["workloads"]
        assert new_config["workloads"]["new-workload"]["model"] == "gpt-4"
        assert refs == []

    def test_rename_workload_updates_agent_references(self):
        """Should update models.agents references when renaming workload."""
        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {"old-workload": {"provider": "openai", "model": "gpt-4"}},
            "models": {
                "agents": {
                    "universal": {"workload": "old-workload"},
                    "inspector": {"workload": "other-workload"},
                },
                "embeddings": {},
                "summarization": {},
            },
        }

        new_config, refs = rename_entity(
            config, "workload", "old-workload", "new-workload"
        )

        assert new_config["models"]["agents"]["universal"]["workload"] == "new-workload"
        assert (
            new_config["models"]["agents"]["inspector"]["workload"] == "other-workload"
        )
        assert "models.agents.universal.workload" in refs
        assert "models.agents.inspector.workload" not in refs

    def test_rename_workload_updates_embeddings_reference(self):
        """Should update models.embeddings reference when renaming workload."""
        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {
                "embed-workload": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                }
            },
            "models": {
                "agents": {},
                "embeddings": {"workload": "embed-workload"},
                "summarization": {},
            },
        }

        new_config, refs = rename_entity(
            config, "workload", "embed-workload", "new-embed"
        )

        assert new_config["models"]["embeddings"]["workload"] == "new-embed"
        assert "models.embeddings.workload" in refs

    def test_rename_workload_updates_summarization_reference(self):
        """Should update models.summarization reference when renaming workload."""
        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {"summary-workload": {"provider": "openai", "model": "gpt-4"}},
            "models": {
                "agents": {},
                "embeddings": {},
                "summarization": {"workload": "summary-workload"},
            },
        }

        new_config, refs = rename_entity(
            config, "workload", "summary-workload", "new-summary"
        )

        assert new_config["models"]["summarization"]["workload"] == "new-summary"
        assert "models.summarization.workload" in refs

    def test_rename_workload_not_found(self):
        """Should raise ValueError if workload doesn't exist."""
        config = {
            "providers": {},
            "workloads": {},
            "models": {},
        }

        with pytest.raises(ValueError) as exc_info:
            rename_entity(config, "workload", "nonexistent", "new-name")

        assert "not found" in str(exc_info.value)

    def test_rename_workload_already_exists(self):
        """Should raise ValueError if new name already exists."""
        config = {
            "providers": {},
            "workloads": {
                "workload-a": {"provider": "openai"},
                "workload-b": {"provider": "openai"},
            },
            "models": {},
        }

        with pytest.raises(ValueError) as exc_info:
            rename_entity(config, "workload", "workload-a", "workload-b")

        assert "already exists" in str(exc_info.value)

    def test_rename_provider_basic(self):
        """Should rename provider and return empty refs if no references."""
        config = {
            "providers": {"old-provider": {"type": "openai", "api_key": "sk-xxx"}},
            "workloads": {},
            "models": {},
        }

        new_config, refs = rename_entity(
            config, "provider", "old-provider", "new-provider"
        )

        assert "old-provider" not in new_config["providers"]
        assert "new-provider" in new_config["providers"]
        assert new_config["providers"]["new-provider"]["api_key"] == "sk-xxx"
        assert refs == []

    def test_rename_provider_updates_workload_references(self):
        """Should update workloads that reference the provider."""
        config = {
            "providers": {
                "old-provider": {"type": "openai"},
                "other-provider": {"type": "openai"},
            },
            "workloads": {
                "workload-a": {"provider": "old-provider", "model": "gpt-4"},
                "workload-b": {"provider": "other-provider", "model": "gpt-4"},
                "workload-c": {"provider": "old-provider", "model": "gpt-5"},
            },
            "models": {},
        }

        new_config, refs = rename_entity(
            config, "provider", "old-provider", "new-provider"
        )

        assert new_config["workloads"]["workload-a"]["provider"] == "new-provider"
        assert new_config["workloads"]["workload-b"]["provider"] == "other-provider"
        assert new_config["workloads"]["workload-c"]["provider"] == "new-provider"
        assert "workloads.workload-a.provider" in refs
        assert "workloads.workload-c.provider" in refs
        assert "workloads.workload-b.provider" not in refs

    def test_rename_provider_not_found(self):
        """Should raise ValueError if provider doesn't exist."""
        config = {
            "providers": {},
            "workloads": {},
            "models": {},
        }

        with pytest.raises(ValueError) as exc_info:
            rename_entity(config, "provider", "nonexistent", "new-name")

        assert "not found" in str(exc_info.value)

    def test_rename_invalid_type(self):
        """Should raise ValueError for invalid entity type."""
        config = {"providers": {}, "workloads": {}, "models": {}}

        with pytest.raises(ValueError) as exc_info:
            rename_entity(config, "invalid", "old", "new")

        assert "Invalid entity_type" in str(exc_info.value)


# =============================================================================
# API endpoint tests
# =============================================================================


@pytest.fixture
async def config_manager_with_workloads(tmp_path: Path):
    """Create a config manager with test workloads."""
    config_path = tmp_path / "config.json"

    initial_config = {
        "providers": {
            "openai": {"type": "openai", "api_key": "sk-test"},
        },
        "workloads": {
            "my-reasoning": {"provider": "openai", "model": "gpt-4"},
            "my-embedding": {"provider": "openai", "model": "text-embedding-3-small"},
        },
        "models": {
            "agents": {
                "universal": {"workload": "my-reasoning"},
                "inspector": {"workload": "my-reasoning"},
            },
            "embeddings": {"workload": "my-embedding"},
            "summarization": {"workload": "my-reasoning"},
        },
    }

    with open(config_path, "w") as f:
        json.dump(initial_config, f)

    defaults = get_default_config()
    provider = LocalFileConfigProvider(config_path, defaults=defaults)
    manager = ConfigManager(provider)
    await manager.initialize()

    import agentsmithy.config.manager as mgr_module

    old_manager = mgr_module._config_manager
    mgr_module._config_manager = manager

    yield manager

    mgr_module._config_manager = old_manager


@pytest.fixture
def client(config_manager_with_workloads):
    """Create test client with config manager."""
    from agentsmithy.api.app import create_app

    app = create_app()
    return TestClient(app)


class TestRenameEndpoint:
    """Tests for POST /api/config/rename endpoint."""

    def test_rename_workload_success(self, client):
        """Should rename workload and update all references."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "my-reasoning",
                "new_name": "gpt4-reasoning",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["old_name"] == "my-reasoning"
        assert data["new_name"] == "gpt4-reasoning"
        assert "gpt4-reasoning" in data["config"]["workloads"]
        assert "my-reasoning" not in data["config"]["workloads"]
        # Check references were updated
        assert "models.agents.universal.workload" in data["updated_references"]
        assert "models.agents.inspector.workload" in data["updated_references"]
        assert "models.summarization.workload" in data["updated_references"]

    def test_rename_provider_success(self, client):
        """Should rename provider and update workload references."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "provider",
                "old_name": "openai",
                "new_name": "openai-main",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "openai-main" in data["config"]["providers"]
        assert "openai" not in data["config"]["providers"]
        # All workloads that reference openai should be updated
        # (includes both user workloads and default workloads merged in)
        assert len(data["updated_references"]) >= 2
        # Check that user workloads were updated
        assert any("my-reasoning" in ref for ref in data["updated_references"])
        assert any("my-embedding" in ref for ref in data["updated_references"])

    def test_rename_workload_not_found(self, client):
        """Should return 400 if workload doesn't exist."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "nonexistent",
                "new_name": "new-name",
            },
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

    def test_rename_workload_already_exists(self, client):
        """Should return 400 if new name already exists."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "my-reasoning",
                "new_name": "my-embedding",  # Already exists
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_rename_invalid_type(self, client):
        """Should return 400 for invalid entity type."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "invalid",
                "old_name": "something",
                "new_name": "other",
            },
        )

        assert response.status_code == 400
        assert "Invalid type" in response.json()["detail"]

    def test_rename_same_name(self, client):
        """Should return 400 if old_name equals new_name."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "my-reasoning",
                "new_name": "my-reasoning",
            },
        )

        assert response.status_code == 400
        assert "must be different" in response.json()["detail"]

    def test_rename_empty_names(self, client):
        """Should return 400 if names are empty."""

        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "",
                "new_name": "new-name",
            },
        )

        assert response.status_code == 400

    def test_rename_persists_to_config(self, client):
        """Rename should be persisted to config file."""

        # Rename
        response = client.post(
            "/api/config/rename",
            json={
                "type": "workload",
                "old_name": "my-reasoning",
                "new_name": "renamed-reasoning",
            },
        )
        assert response.status_code == 200

        # Get config to verify persistence
        response = client.get("/api/config")
        assert response.status_code == 200
        config = response.json()["config"]

        assert "renamed-reasoning" in config["workloads"]
        assert "my-reasoning" not in config["workloads"]
        assert (
            config["models"]["agents"]["universal"]["workload"] == "renamed-reasoning"
        )
