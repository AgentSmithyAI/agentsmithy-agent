"""Tests for setting API keys via configuration endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.config.manager import ConfigManager
from agentsmithy.config.providers import LocalFileConfigProvider
from agentsmithy.config.settings import Settings


@pytest.fixture
def config_file(tmp_path: Path):
    """Create a temporary config file."""
    config_path = tmp_path / "config.json"
    initial_config = {
        "model": "gpt-4",
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


def test_set_openai_api_key(client: TestClient):
    """Test setting OpenAI API key via config endpoint."""
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-test-key-12345",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    config = data["config"]

    # Verify the key was set
    assert "providers" in config
    assert "openai" in config["providers"]
    assert config["providers"]["openai"]["api_key"] == "sk-test-key-12345"


def test_set_openai_api_key_with_base_url(client: TestClient):
    """Test setting OpenAI API key with custom base URL."""
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-custom-key",
                    "base_url": "https://custom.openai.proxy.com/v1",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    config = data["config"]
    assert config["providers"]["openai"]["api_key"] == "sk-custom-key"
    assert (
        config["providers"]["openai"]["base_url"]
        == "https://custom.openai.proxy.com/v1"
    )


def test_set_openai_api_key_persists_to_file(client: TestClient, config_file: Path):
    """Test that API key is persisted to config file."""
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-persistent-key",
                    "base_url": "https://api.openai.com/v1",
                }
            }
        }
    }

    response = client.put("/api/config", json=update_data)
    assert response.status_code == 200

    # Read the config file directly
    saved_config = json.loads(config_file.read_text())

    assert "providers" in saved_config
    assert "openai" in saved_config["providers"]
    assert saved_config["providers"]["openai"]["api_key"] == "sk-persistent-key"
    assert (
        saved_config["providers"]["openai"]["base_url"] == "https://api.openai.com/v1"
    )


def test_set_multiple_provider_keys(client: TestClient):
    """Test setting API keys for multiple providers."""
    update_data = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-openai-key",
                    "base_url": "https://api.openai.com/v1",
                },
                "anthropic": {
                    "api_key": "sk-ant-key",
                    "base_url": "https://api.anthropic.com",
                },
            }
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    data = response.json()

    config = data["config"]
    assert config["providers"]["openai"]["api_key"] == "sk-openai-key"
    assert config["providers"]["anthropic"]["api_key"] == "sk-ant-key"


def test_update_existing_api_key(client: TestClient):
    """Test updating an existing API key."""
    # First set
    update_data1 = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-old-key",
                }
            }
        }
    }
    response1 = client.put("/api/config", json=update_data1)
    assert response1.status_code == 200

    # Then update
    update_data2 = {
        "config": {
            "providers": {
                "openai": {
                    "api_key": "sk-new-key",
                }
            }
        }
    }
    response2 = client.put("/api/config", json=update_data2)
    assert response2.status_code == 200

    # Verify the key was updated
    config = response2.json()["config"]
    assert config["providers"]["openai"]["api_key"] == "sk-new-key"


def test_api_key_accessible_via_settings(config_manager: ConfigManager):
    """Test that API key set via config is accessible through Settings."""
    # Update config with API key
    import asyncio

    async def set_key():
        await config_manager.update(
            {
                "providers": {
                    "openai": {
                        "api_key": "sk-settings-test-key",
                        "base_url": "https://api.openai.com/v1",
                    }
                }
            }
        )

    asyncio.run(set_key())

    # Access via Settings
    settings = Settings(config_manager)

    assert settings.openai_api_key == "sk-settings-test-key"
    assert settings.openai_base_url == "https://api.openai.com/v1"


def test_set_embedding_model_and_key(client: TestClient):
    """Test setting embedding model configuration."""
    update_data = {
        "config": {
            "embedding_model": "text-embedding-3-large",
            "providers": {
                "openai": {
                    "api_key": "sk-embedding-key",
                }
            },
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    config = response.json()["config"]

    assert config["embedding_model"] == "text-embedding-3-large"
    assert config["providers"]["openai"]["api_key"] == "sk-embedding-key"


def test_set_model_with_provider_config(client: TestClient):
    """Test setting model along with provider configuration."""
    update_data = {
        "config": {
            "models": {
                "agents": {
                    "universal": {
                        "workload": "reasoning",
                    }
                }
            },
            "workloads": {
                "reasoning": {
                    "provider": "openai",
                    "model": "gpt-4-turbo",
                }
            },
            "providers": {
                "openai": {
                    "api_key": "sk-model-key",
                    "base_url": "https://api.openai.com/v1",
                }
            },
        }
    }

    response = client.put("/api/config", json=update_data)

    assert response.status_code == 200
    config = response.json()["config"]

    assert config["models"]["agents"]["universal"]["workload"] == "reasoning"
    assert (
        config["workloads"]["reasoning"]["model"] == "gpt-4-turbo"
    ), "workload model should be updated"
    assert config["workloads"]["reasoning"]["provider"] == "openai"
    assert config["providers"]["openai"]["api_key"] == "sk-model-key"
