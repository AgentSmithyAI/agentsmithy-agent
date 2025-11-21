"""Tests for configuration API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.config.manager import ConfigManager
from agentsmithy.config.providers import LocalFileConfigProvider


@pytest.fixture
def config_file(tmp_path: Path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.json"
    initial_config = {
        "workloads": {"reasoning": {"model": "gpt-4"}},
    }
    config_path.write_text(json.dumps(initial_config, indent=2))
    return config_path


@pytest.fixture
async def config_manager(config_file: Path):
    """Create a config manager with temporary config file."""
    defaults = {
        "server_host": "localhost",
        "server_port": 8765,
    }

    provider = LocalFileConfigProvider(config_file, defaults=defaults)
    manager = ConfigManager(provider)
    await manager.initialize()

    # Set as global instance
    import agentsmithy.config.manager as mgr_module

    old_manager = mgr_module._config_manager
    mgr_module._config_manager = manager

    yield manager

    # Restore old manager
    mgr_module._config_manager = old_manager


@pytest.fixture
def client(config_manager: ConfigManager):
    """Create FastAPI test client with config manager."""
    app = create_app()
    app.state.config_manager = config_manager
    return TestClient(app)


def test_get_config(client: TestClient):
    """Test GET /api/config endpoint."""
    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()

    assert "config" in data
    assert "metadata" in data
    config = data["config"]
    metadata = data["metadata"]

    # Check that user config values are present
    assert config["workloads"]["reasoning"]["model"] == "gpt-4"

    # Check that defaults are present
    assert config["server_host"] == "localhost"
    assert config["server_port"] == 8765

    # Metadata should provide provider info
    assert "provider_types" in metadata
    assert isinstance(metadata["provider_types"], list)
    assert "workloads" in metadata
    assert any(w["name"] == "reasoning" for w in metadata["workloads"])
    assert "model_catalog" in metadata
    assert "openai" in metadata["model_catalog"]
    assert isinstance(metadata["model_catalog"]["openai"].get("chat", []), list)


def test_update_config(client: TestClient):
    """Test PUT /api/config endpoint."""
    update_data = {"config": {"workloads": {"reasoning": {"model": "gpt-4-turbo"}}}}

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "Successfully updated 1 configuration key(s)" in data["message"]
    assert "metadata" in data

    # Check updated config
    config = data["config"]
    assert config["workloads"]["reasoning"]["model"] == "gpt-4-turbo"


def test_update_config_persists(client: TestClient, config_file: Path):
    """Test that configuration updates are persisted to file."""
    update_data = {
        "config": {
            "server_port": 9999,
            "workloads": {"reasoning": {"model": "gpt-3.5-turbo"}},
        }
    }

    response = client.put("/api/config", json=update_data)
    assert response.status_code == 200

    # Read the config file directly
    saved_config = json.loads(config_file.read_text())

    assert saved_config["server_port"] == 9999
    assert saved_config["workloads"]["reasoning"]["model"] == "gpt-3.5-turbo"


def test_update_config_empty(client: TestClient):
    """Test PUT /api/config with empty config dict."""
    update_data = {"config": {}}

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "Successfully updated 0 configuration key(s)" in data["message"]
    assert "metadata" in data


def test_update_config_nested(client: TestClient):
    """Test updating nested configuration values."""
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "test-key-123",
                    "base_url": "https://api.openai.com",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    config = data["config"]

    # Check nested values
    assert "providers" in config
    assert "openai" in config["providers"]
    assert config["providers"]["openai"]["api_key"] == "test-key-123"
    assert config["providers"]["openai"]["base_url"] == "https://api.openai.com"


def test_get_config_after_update(client: TestClient):
    """Test that GET reflects PUT changes."""
    # First, get initial config
    response1 = client.get("/api/config")
    assert response1.status_code == 200
    initial_model = response1.json()["config"]["workloads"]["reasoning"]["model"]
    assert initial_model == "gpt-4"

    # Update config
    update_data = {"config": {"workloads": {"reasoning": {"model": "claude-3-sonnet"}}}}
    response2 = client.put("/api/config", json=update_data)
    assert response2.status_code == 200

    # Get config again
    response3 = client.get("/api/config")
    assert response3.status_code == 200
    updated_model = response3.json()["config"]["workloads"]["reasoning"]["model"]
    assert updated_model == "claude-3-sonnet"


def test_update_config_invalid_json(client: TestClient):
    """Test PUT /api/config with invalid request body."""
    # Missing 'config' key
    response = client.put("/api/config", json={"invalid": "data"})

    assert response.status_code == 422  # Validation error


def test_update_config_rejects_invalid_provider_type(client: TestClient):
    """Provider type must be one of the allowed enum values."""
    update_data = {
        "config": {
            "providers": {
                "custom-llm": {
                    "type": "totally-unknown",
                    "model": "my-model",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "errors" in detail
    assert any("unsupported type" in err for err in detail["errors"])


def test_update_config_rejects_unknown_agent_provider(client: TestClient):
    """Agent provider reference must exist in providers section."""
    update_data = {
        "config": {
            "models": {
                "agents": {
                    "universal": {"workload": "does-not-exist"},
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert any("unknown workload" in err for err in detail["errors"])
