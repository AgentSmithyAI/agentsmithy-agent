"""Test that config changes via API are applied without server restart."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

import agentsmithy.config.manager as mgr_module
from agentsmithy.api.app import create_app
from agentsmithy.config.providers import LocalFileConfigProvider
from agentsmithy.config.settings import Settings

if TYPE_CHECKING:
    from agentsmithy.config.manager import ConfigManager


@pytest.fixture
def config_file(tmp_path: Path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.json"
    initial_config = {
        "providers": {
            "openai": {
                "api_key": "sk-initial-key",
                "base_url": "https://api.openai.com/v1",
            }
        }
    }
    config_path.write_text(json.dumps(initial_config, indent=2))
    return config_path


@pytest.fixture
async def config_manager(config_file: Path):
    """Create a config manager with temporary config file."""
    defaults = {"server_host": "localhost", "server_port": 8765}

    provider = LocalFileConfigProvider(config_file, defaults=defaults)
    manager = mgr_module.ConfigManager(provider)
    await manager.initialize()

    # Set as global instance
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


def test_config_update_triggers_callback(config_manager: ConfigManager):
    """Test that config update via manager triggers callbacks."""
    callback_called = False
    callback_config = None

    def test_callback(new_config):
        nonlocal callback_called, callback_config
        callback_called = True
        callback_config = new_config

    config_manager.register_change_callback(test_callback)

    # Update config
    import asyncio

    asyncio.run(config_manager.update({"test_key": "test_value"}))

    assert callback_called is True
    assert callback_config is not None
    assert callback_config.get("test_key") == "test_value"


def test_api_endpoint_triggers_callback(
    client: TestClient, config_manager: ConfigManager
):
    """Test that config update via API endpoint triggers callbacks."""
    callback_called = False
    callback_keys = []

    def test_callback(new_config):
        nonlocal callback_called, callback_keys
        callback_called = True
        callback_keys = list(new_config.keys())

    config_manager.register_change_callback(test_callback)

    # Update via API
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-new-key-via-api",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)
    assert response.status_code == 200

    # Verify callback was triggered
    assert callback_called is True
    assert "providers" in callback_keys


def test_config_changes_accessible_immediately(
    client: TestClient, config_manager: ConfigManager
):
    """Test that config changes are immediately accessible."""
    # Get initial config
    response1 = client.get("/api/config")
    initial_key = response1.json()["config"]["providers"]["openai"]["api_key"]
    assert initial_key == "sk-initial-key"

    # Update config
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-updated-key",
                }
            }
        }
    }
    response2 = client.put("/api/config", json=update_data)
    assert response2.status_code == 200

    # Get config again - should see new value immediately
    response3 = client.get("/api/config")
    updated_key = response3.json()["config"]["providers"]["openai"]["api_key"]
    assert updated_key == "sk-updated-key"

    # Also verify via Settings
    settings = Settings(config_manager)
    provider_config = settings.get_provider_config("openai")
    assert provider_config.get("api_key") == "sk-updated-key"


def test_multiple_callbacks_all_triggered(config_manager: ConfigManager):
    """Test that multiple registered callbacks are all triggered."""
    callback1_called = False
    callback2_called = False

    def callback1(new_config):
        nonlocal callback1_called
        callback1_called = True

    def callback2(new_config):
        nonlocal callback2_called
        callback2_called = True

    config_manager.register_change_callback(callback1)
    config_manager.register_change_callback(callback2)

    # Update config
    import asyncio

    asyncio.run(config_manager.update({"test": "value"}))

    assert callback1_called is True
    assert callback2_called is True
