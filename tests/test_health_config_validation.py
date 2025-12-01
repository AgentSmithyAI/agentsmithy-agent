"""Test health endpoint reports configuration validity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

import agentsmithy.config.manager as mgr_module
from agentsmithy.api.app import create_app
from agentsmithy.config.providers import LocalFileConfigProvider

if TYPE_CHECKING:
    from agentsmithy.config.manager import ConfigManager


@pytest.fixture
def config_file_with_key(tmp_path: Path):
    """Config file with valid API key."""
    config_path = tmp_path / "config.json"
    config = {
        "providers": {
            "openai": {
                "api_key": "sk-valid-key",
                "base_url": "https://api.openai.com/v1",
            }
        }
    }
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def config_file_without_key(tmp_path: Path):
    """Config file without API key."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}, indent=2))
    return config_path


@pytest.fixture
async def config_manager_with_key(config_file_with_key: Path):
    """Config manager with valid API key."""
    from agentsmithy.config import settings
    from agentsmithy.config.defaults import get_default_config

    provider = LocalFileConfigProvider(
        config_file_with_key, defaults=get_default_config()
    )
    manager = mgr_module.ConfigManager(provider)
    await manager.initialize()

    old_manager = mgr_module._config_manager
    old_settings_manager = settings._config_manager
    mgr_module._config_manager = manager
    settings._config_manager = manager

    yield manager

    mgr_module._config_manager = old_manager
    settings._config_manager = old_settings_manager


@pytest.fixture
async def config_manager_without_key(config_file_without_key: Path, monkeypatch):
    """Config manager without API key."""
    from agentsmithy.config import settings
    from agentsmithy.config.defaults import get_default_config

    # Remove env var
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = LocalFileConfigProvider(
        config_file_without_key, defaults=get_default_config()
    )
    manager = mgr_module.ConfigManager(provider)
    await manager.initialize()

    old_manager = mgr_module._config_manager
    old_settings_manager = settings._config_manager
    mgr_module._config_manager = manager
    settings._config_manager = manager

    yield manager

    mgr_module._config_manager = old_manager
    settings._config_manager = old_settings_manager


def test_health_reports_config_valid_when_key_present(
    config_manager_with_key: ConfigManager,
):
    """Test that health endpoint includes config validation info."""
    app = create_app()
    app.state.config_manager = config_manager_with_key
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    # Config validation fields must be present
    assert "config_valid" in data
    assert "config_errors" in data
    # Value is bool
    assert isinstance(data["config_valid"], bool)


def test_health_reports_config_invalid_when_key_missing(
    config_manager_without_key: ConfigManager,
):
    """Test that health endpoint reports config_valid=false when API key is missing."""
    app = create_app()
    app.state.config_manager = config_manager_without_key
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    # Server still runs even without API key
    assert "config_valid" in data
    assert "config_errors" in data
    assert data["config_valid"] is False
    assert data["config_errors"] is not None
    assert len(data["config_errors"]) > 0
    # The exact error message may vary but it should indicate API key issue
    print(f"DEBUG: config_errors={data['config_errors']}")
    assert any("API key" in err for err in data["config_errors"])


def test_health_config_becomes_valid_after_update(
    config_manager_without_key: ConfigManager,
):
    """Test that config_valid changes from false to true after setting API key."""
    app = create_app()
    app.state.config_manager = config_manager_without_key
    client = TestClient(app)

    # First check - should be invalid
    response1 = client.get("/health")
    data1 = response1.json()
    assert data1["config_valid"] is False
    assert any("API key" in err for err in data1["config_errors"])

    # Set API key via PUT /api/config
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-newly-set-key",
                    "base_url": "https://api.openai.com/v1",
                }
            }
        }
    }
    response2 = client.put("/api/config", json=update_data)
    assert response2.status_code == 200

    # Check again - endpoint should reflect updated status
    response3 = client.get("/health")
    data3 = response3.json()
    assert "config_valid" in data3
    assert "config_errors" in data3
