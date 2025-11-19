"""Tests for configuration manager."""

import json
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from agentsmithy.config import (
    ConfigManager,
    LayeredConfigProvider,
    LocalFileConfigProvider,
    Settings,
    get_default_config,
)


@pytest.mark.asyncio
async def test_local_file_provider_creates_default_config():
    """Test that LocalFileConfigProvider creates config with defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {"key1": "value1", "key2": 42}

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        config = await provider.load()

        assert config == defaults
        assert config_path.exists()


@pytest.mark.asyncio
async def test_local_file_provider_loads_existing_config():
    """Test that LocalFileConfigProvider loads existing config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        # Create config file
        existing_config = {"key1": "existing", "key2": 100}
        config_path.write_text(json.dumps(existing_config), encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults={"key1": "default"})
        config = await provider.load()

        # Should merge with defaults
        assert config["key1"] == "existing"
        assert config["key2"] == 100


@pytest.mark.asyncio
async def test_local_file_provider_saves_config():
    """Test that LocalFileConfigProvider saves config atomically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        provider = LocalFileConfigProvider(config_path)
        config = {"key": "value"}

        await provider.save(config)

        assert config_path.exists()
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["key"] == "value"
        assert "providers" in saved_config
        assert "workloads" in saved_config


@pytest.mark.asyncio
async def test_local_file_provider_normalizes_legacy_providers():
    """Legacy provider entries should be dropped in favour of workloads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = get_default_config()

        legacy_config = {
            "providers": {
                "openai": deepcopy(defaults["providers"]["openai"]),
                "gpt5": {
                    "type": "openai",
                    "model": "gpt-5",
                    "options": {},
                },
            },
            "models": {
                "agents": {
                    "universal": {"provider": "gpt5"},
                }
            },
        }
        config_path.write_text(json.dumps(legacy_config), encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        config = await provider.load()

        assert "gpt5" not in config["providers"]
        assert "provider" not in config["models"]["agents"]["universal"]

        persisted = json.loads(config_path.read_text(encoding="utf-8"))
        assert "gpt5" in persisted["providers"]
        assert persisted["models"]["agents"]["universal"]["provider"] == "gpt5"


@pytest.mark.asyncio
async def test_local_file_provider_rejects_invalid_workload_refs():
    """Configs referencing unknown providers should fail to load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = get_default_config()

        invalid_config = {
            "providers": deepcopy(defaults["providers"]),
            "workloads": {
                "custom": {"provider": "missing", "model": "foo"},
            },
            "models": {
                "agents": {
                    "universal": {"workload": "custom"},
                }
            },
        }
        config_path.write_text(json.dumps(invalid_config), encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        with pytest.raises(ValueError):
            await provider.load()


@pytest.mark.asyncio
async def test_config_manager_initialization():
    """Test ConfigManager initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = get_default_config()

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        manager = ConfigManager(provider)

        await manager.initialize()

        assert (
            manager.get("models")["agents"]["universal"]["workload"]
            == defaults["models"]["agents"]["universal"]["workload"]
        )


@pytest.mark.asyncio
async def test_config_manager_typed_getters():
    """Test ConfigManager typed getter methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {
            "str_key": "hello",
            "int_key": 42,
            "float_key": 3.14,
            "bool_key": True,
        }

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        manager = ConfigManager(provider)
        await manager.initialize()

        assert manager.get_str("str_key", "") == "hello"
        assert manager.get_int("int_key", 0) == 42
        assert manager.get_float("float_key", 0.0) == 3.14
        assert manager.get_bool("bool_key", False) is True


@pytest.mark.asyncio
async def test_config_manager_set_and_update():
    """Test ConfigManager set and update methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        provider = LocalFileConfigProvider(config_path, defaults={})
        manager = ConfigManager(provider)
        await manager.initialize()

        # Test set
        await manager.set("key1", "value1")
        assert manager.get("key1") == "value1"

        # Test update
        await manager.update({"key2": "value2", "key3": "value3"})
        assert manager.get("key2") == "value2"
        assert manager.get("key3") == "value3"

        # Verify persistence
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["key1"] == "value1"
        assert saved_config["key2"] == "value2"


@pytest.mark.asyncio
async def test_config_manager_callbacks():
    """Test ConfigManager change callbacks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        provider = LocalFileConfigProvider(config_path, defaults={})
        manager = ConfigManager(provider)
        await manager.initialize()

        callback_called = False
        received_config = None

        def callback(config):
            nonlocal callback_called, received_config
            callback_called = True
            received_config = config

        manager.register_change_callback(callback)

        await manager.set("key", "value")

        assert callback_called
        assert received_config["key"] == "value"


@pytest.mark.asyncio
async def test_settings_with_config_manager():
    """Test Settings class integration with ConfigManager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = get_default_config()

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        manager = ConfigManager(provider)
        await manager.initialize()

        # Create settings with manager
        settings = Settings(config_manager=manager)

        # Test property access
        # With new structure, model is resolved from workload definition
        workload_name = defaults["models"]["agents"]["universal"]["workload"]
        expected_model = defaults["workloads"][workload_name]["model"]
        assert settings.model == expected_model
        assert settings.streaming_enabled == defaults["streaming_enabled"]


def test_settings_env_fallback():
    """Test Settings falls back to environment variables."""
    import os

    # Set env var (using new key name)
    os.environ["MODEL"] = "test-model"

    # Settings without config manager should use env
    settings = Settings(config_manager=None)
    assert settings.model == "test-model"

    # Cleanup
    del os.environ["MODEL"]


@pytest.mark.asyncio
async def test_invalid_json_uses_last_valid_config():
    """Test that invalid JSON doesn't reset config to defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {"key": "default_value"}

        provider = LocalFileConfigProvider(config_path, defaults=defaults)

        # First load - creates with defaults
        config1 = await provider.load()
        assert config1["key"] == "default_value"

        # Update config
        await provider.save({"key": "updated_value"})
        config2 = await provider.load()
        assert config2["key"] == "updated_value"

        # Corrupt the JSON file
        config_path.write_text("{ invalid json }", encoding="utf-8")

        # Load should return last valid config, not defaults
        config3 = await provider.load()
        assert config3["key"] == "updated_value"  # Not "default_value"!


@pytest.mark.asyncio
async def test_invalid_json_on_first_load_uses_defaults():
    """Test that invalid JSON on first load uses defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {"key": "default_value"}

        # Create invalid JSON file
        config_path.write_text("{ invalid json }", encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        config = await provider.load()

        # Should use defaults since no previous valid config exists
        assert config["key"] == "default_value"


@pytest.mark.asyncio
async def test_json_decode_error_logging():
    """Test that JSON syntax errors are logged with line/column info."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        # Create invalid JSON
        config_path.write_text('{\n  "key": invalid\n}', encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults={})

        # Should not raise, but log the error
        config = await provider.load()
        assert config == {}  # Returns defaults


@pytest.mark.asyncio
async def test_layered_config_provider_merges_global_and_local(tmp_path: Path):
    """Ensure LayeredConfigProvider merges global and local configs correctly."""
    global_path = tmp_path / "global.json"
    local_path = tmp_path / "local.json"

    defaults = {"key": "default", "shared": "base"}
    provider = LayeredConfigProvider(
        [
            LocalFileConfigProvider(global_path, defaults=defaults),
            LocalFileConfigProvider(local_path, defaults={}, create_if_missing=False),
        ]
    )

    merged = await provider.load()
    assert merged["key"] == "default"
    assert merged["shared"] == "base"

    # Update global config via provider.save
    await provider.save({"key": "global", "global_only": "g"})
    merged = await provider.load()
    assert merged["key"] == "global"
    assert merged["global_only"] == "g"

    # Write local override directly
    local_path.write_text(json.dumps({"key": "local", "local_only": "l"}))
    merged = await provider.load()
    assert merged["key"] == "local"
    assert merged["local_only"] == "l"
    # Global-only field should still exist
    assert merged["global_only"] == "g"


@pytest.mark.asyncio
async def test_config_manager_with_local_overrides(tmp_path: Path):
    """ConfigManager should respect local overrides via layered provider."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    global_path = global_dir / "config.json"
    local_path = tmp_path / "project" / "config.json"
    local_path.parent.mkdir()

    defaults = {"value": "default"}
    provider = LayeredConfigProvider(
        [
            LocalFileConfigProvider(global_path, defaults=defaults),
            LocalFileConfigProvider(local_path, defaults={}, create_if_missing=False),
        ]
    )
    manager = ConfigManager(provider)
    await manager.initialize()

    # Update via manager -> should persist to global config
    await manager.set("value", "global")
    saved_global = json.loads(global_path.read_text(encoding="utf-8"))
    assert saved_global["value"] == "global"

    # Local override should take precedence after reload
    local_path.write_text(json.dumps({"value": "local"}), encoding="utf-8")
    new_config = await provider.load()
    manager._config = new_config
    assert manager.get("value") == "local"
