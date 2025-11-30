"""Tests for workloads in API - ensuring client uses workloads, not model_catalog.

These tests verify that:
1. API metadata returns workloads that can be used for dropdown selection
2. Workload names are what goes into config, not model names
3. PUT with workload name correctly updates config
4. Client workflow: GET metadata → select workload → PUT config
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.config import get_default_config
from agentsmithy.config.manager import ConfigManager
from agentsmithy.config.providers import LocalFileConfigProvider


@pytest.fixture
def defaults():
    """Get default config with auto-generated workloads."""
    return get_default_config()


@pytest.fixture
async def config_manager_with_defaults(tmp_path: Path, defaults):
    """Create config manager with full defaults including auto-generated workloads."""
    config_path = tmp_path / "config.json"

    provider = LocalFileConfigProvider(config_path, defaults=defaults)
    manager = ConfigManager(provider)
    await manager.initialize()

    import agentsmithy.config.manager as mgr_module

    old_manager = mgr_module._config_manager
    mgr_module._config_manager = manager

    yield manager

    mgr_module._config_manager = old_manager


@pytest.fixture
def client(config_manager_with_defaults):
    """Create test client with config manager."""
    from agentsmithy.api.app import create_app

    app = create_app()
    return TestClient(app)


class TestWorkloadsInMetadata:
    """Tests that metadata.workloads is what client should use for selection."""

    def test_metadata_contains_workloads_list(self, client):
        """API should return workloads list in metadata."""
        response = client.get("/api/config")
        assert response.status_code == 200

        data = response.json()
        assert "metadata" in data
        assert "workloads" in data["metadata"]
        assert isinstance(data["metadata"]["workloads"], list)
        assert len(data["metadata"]["workloads"]) > 0

    def test_workloads_have_name_field(self, client):
        """Each workload should have 'name' field for dropdown value."""
        response = client.get("/api/config")
        data = response.json()

        for workload in data["metadata"]["workloads"]:
            assert "name" in workload, "Workload must have 'name' for dropdown"

    def test_workload_names_match_config_workloads(self, client, defaults):
        """Workload names in metadata should match config workloads keys."""
        response = client.get("/api/config")
        data = response.json()

        metadata_names = {w["name"] for w in data["metadata"]["workloads"]}
        config_names = set(data["config"]["workloads"].keys())

        assert (
            metadata_names == config_names
        ), "Metadata workload names must match config workload keys"


class TestWorkloadSelectionFlow:
    """Tests the full client workflow: see options → select → apply."""

    def test_select_workload_from_metadata_and_apply(self, client):
        """Client should be able to select workload from metadata and PUT config."""
        # Step 1: GET metadata to see available workloads
        get_response = client.get("/api/config")
        assert get_response.status_code == 200
        metadata = get_response.json()["metadata"]

        # Step 2: Get workload names (this is what goes in dropdown)
        workload_names = [w["name"] for w in metadata["workloads"]]
        assert len(workload_names) > 0

        # Step 3: Select a workload (e.g., first one that's not current)
        current_workload = get_response.json()["config"]["models"]["agents"][
            "universal"
        ]["workload"]
        new_workload = next(
            (w for w in workload_names if w != current_workload), workload_names[0]
        )

        # Step 4: PUT with the selected WORKLOAD NAME (not model name!)
        put_response = client.put(
            "/api/config",
            json={
                "config": {
                    "models": {"agents": {"universal": {"workload": new_workload}}}
                }
            },
        )
        assert put_response.status_code == 200

        # Step 5: Verify the change was applied
        verify_response = client.get("/api/config")
        actual_workload = verify_response.json()["config"]["models"]["agents"][
            "universal"
        ]["workload"]
        assert actual_workload == new_workload

    def test_workload_name_is_what_goes_to_config_not_model(self, client):
        """Explicitly verify that workload NAME goes to config, not model name."""
        # Get a workload
        response = client.get("/api/config")
        workloads = response.json()["metadata"]["workloads"]

        # Pick one workload
        workload = workloads[0]
        workload_name = workload["name"]

        # PUT using workload name
        put_response = client.put(
            "/api/config",
            json={
                "config": {
                    "models": {"agents": {"universal": {"workload": workload_name}}}
                }
            },
        )
        assert put_response.status_code == 200

        # Verify config has workload NAME
        config = put_response.json()["config"]
        assert config["models"]["agents"]["universal"]["workload"] == workload_name

    def test_cannot_use_nonexistent_workload_name(self, client):
        """If workload doesn't exist, PUT should fail validation."""
        # Try to use a workload name that doesn't exist
        put_response = client.put(
            "/api/config",
            json={
                "config": {
                    "models": {
                        "agents": {"universal": {"workload": "nonexistent-model-xyz"}}
                    }
                }
            },
        )
        # Should fail because no workload with that name exists
        assert put_response.status_code == 400


class TestAgentProviderSlots:
    """Tests for agent_provider_slots which shows what can be configured."""

    def test_agent_slots_show_current_workload(self, client):
        """agent_provider_slots should show current workload selection."""
        response = client.get("/api/config")
        data = response.json()

        slots = data["metadata"]["agent_provider_slots"]
        assert len(slots) > 0

        # Each slot should have current workload
        for slot in slots:
            assert "workload" in slot
            assert "path" in slot

    def test_agent_slots_workload_matches_config(self, client):
        """Workload in slots should match actual config value."""
        response = client.get("/api/config")
        data = response.json()

        config = data["config"]
        slots = data["metadata"]["agent_provider_slots"]

        # Find universal agent slot
        universal_slot = next((s for s in slots if "universal" in s["path"]), None)
        assert universal_slot is not None

        # Should match config
        config_workload = config["models"]["agents"]["universal"]["workload"]
        assert universal_slot["workload"] == config_workload


class TestCustomWorkloadSelection:
    """Tests for selecting custom user-defined workloads."""

    def test_user_can_create_and_select_custom_workload(self, client):
        """User can create custom workload and select it for an agent."""
        # Step 1: Create custom workload and provider
        put_response = client.put(
            "/api/config",
            json={
                "config": {
                    "providers": {
                        "custom-provider": {
                            "type": "openai",
                            "api_key": "test-key",
                            "base_url": "https://custom.api/v1",
                        }
                    },
                    "workloads": {
                        "my-custom-model": {
                            "provider": "custom-provider",
                            "model": "custom-model-name",
                            "options": {},
                        }
                    },
                }
            },
        )
        assert put_response.status_code == 200

        # Step 2: Verify custom workload appears in metadata
        get_response = client.get("/api/config")
        workload_names = [
            w["name"] for w in get_response.json()["metadata"]["workloads"]
        ]
        assert "my-custom-model" in workload_names

        # Step 3: Select custom workload for universal agent
        select_response = client.put(
            "/api/config",
            json={
                "config": {
                    "models": {"agents": {"universal": {"workload": "my-custom-model"}}}
                }
            },
        )
        assert select_response.status_code == 200

        # Step 4: Verify it's applied
        verify_response = client.get("/api/config")
        actual = verify_response.json()["config"]["models"]["agents"]["universal"][
            "workload"
        ]
        assert actual == "my-custom-model"


class TestModelCatalogVsWorkloads:
    """Tests clarifying the difference between model_catalog and workloads."""

    def test_model_catalog_is_for_reference_only(self, client):
        """model_catalog shows known models, but workloads is what client uses."""
        response = client.get("/api/config")
        data = response.json()

        # Both exist
        assert "model_catalog" in data["metadata"]
        assert "workloads" in data["metadata"]

        # Workloads is what client uses for selection
        workloads = data["metadata"]["workloads"]
        assert all("name" in w for w in workloads)

        # model_catalog is just reference (grouped by vendor)
        catalog = data["metadata"]["model_catalog"]
        assert isinstance(catalog, dict)
        # It doesn't have 'name' field per model - it's just lists

    def test_workloads_not_model_catalog_used_for_config(self, client):
        """Config expects workload name, which comes from metadata.workloads."""
        response = client.get("/api/config")
        data = response.json()

        # Get first workload name
        workload_name = data["metadata"]["workloads"][0]["name"]

        # This should work - workload name goes to config
        put_response = client.put(
            "/api/config",
            json={
                "config": {
                    "models": {"agents": {"universal": {"workload": workload_name}}}
                }
            },
        )
        assert put_response.status_code == 200

        # Config should have the workload name
        result = put_response.json()["config"]["models"]["agents"]["universal"][
            "workload"
        ]
        assert result == workload_name


class TestAllAgentSlots:
    """Tests for all configurable agent slots."""

    @pytest.mark.parametrize(
        "slot_path,config_path",
        [
            (
                "models.agents.universal.workload",
                ["models", "agents", "universal", "workload"],
            ),
            (
                "models.agents.inspector.workload",
                ["models", "agents", "inspector", "workload"],
            ),
            ("models.embeddings.workload", ["models", "embeddings", "workload"]),
            ("models.summarization.workload", ["models", "summarization", "workload"]),
        ],
    )
    def test_each_slot_can_be_configured_with_workload(
        self, client, slot_path, config_path
    ):
        """Each agent slot should accept workload from metadata.workloads."""
        # Get available workloads
        response = client.get("/api/config")
        workloads = response.json()["metadata"]["workloads"]

        # Pick appropriate workload (embedding for embeddings, chat for others)
        if "embeddings" in slot_path:
            workload = next(
                (w for w in workloads if "embedding" in w["name"]), workloads[0]
            )
        else:
            workload = next(
                (w for w in workloads if "embedding" not in w["name"]), workloads[0]
            )

        # Build nested update
        update = {}
        current = update
        for key in config_path[:-1]:
            current[key] = {}
            current = current[key]
        current[config_path[-1]] = workload["name"]

        # PUT with config wrapper
        put_response = client.put("/api/config", json={"config": update})
        assert put_response.status_code == 200

        # Verify
        verify_response = client.get("/api/config")
        config = verify_response.json()["config"]

        # Navigate to the value
        value = config
        for key in config_path:
            value = value[key]

        assert value == workload["name"]
