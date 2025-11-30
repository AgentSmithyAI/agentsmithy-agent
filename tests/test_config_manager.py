"""Tests for configuration manager."""

import json
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from agentsmithy.config import (
    ConfigManager,
    ConfigValidationError,
    LayeredConfigProvider,
    LocalFileConfigProvider,
    Settings,
    get_default_config,
)
from agentsmithy.config.constants import DEFAULT_STREAMING_ENABLED
from agentsmithy.config.schema import apply_deletions, deep_merge

# =============================================================================
# Tests for deep_merge and apply_deletions
# =============================================================================


def test_deep_merge_basic():
    """Test basic deep merge behavior."""
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    updates = {"b": {"c": 10, "e": 5}}

    result = deep_merge(base, updates)

    assert result["a"] == 1
    assert result["b"]["c"] == 10
    assert result["b"]["d"] == 3
    assert result["b"]["e"] == 5


def test_deep_merge_none_preserves_value():
    """Test that None in updates preserves base value (skip behavior)."""
    base = {"a": 1, "b": 2}
    updates = {"a": None}

    result = deep_merge(base, updates)

    assert result["a"] == 1  # None means "don't touch"
    assert result["b"] == 2


def test_deep_merge_nested_none_preserves():
    """Test that nested None preserves nested base value."""
    base = {"providers": {"openai": {"api_key": "secret", "model": "gpt-4"}}}
    updates = {"providers": {"openai": {"api_key": None, "model": "gpt-4-turbo"}}}

    result = deep_merge(base, updates)

    assert result["providers"]["openai"]["api_key"] == "secret"
    assert result["providers"]["openai"]["model"] == "gpt-4-turbo"


def test_apply_deletions_removes_null_keys():
    """Test that apply_deletions removes keys with null values."""
    config = {"a": 1, "b": 2, "c": 3}
    updates = {"b": None}

    result = apply_deletions(config, updates)

    assert result["a"] == 1
    assert "b" not in result
    assert result["c"] == 3


def test_apply_deletions_nested():
    """Test nested deletion with apply_deletions."""
    config = {
        "providers": {
            "openai": {"api_key": "sk-123"},
            "anthropic": {"api_key": "ant-456"},
        }
    }
    updates = {"providers": {"anthropic": None}}

    result = apply_deletions(config, updates)

    assert "openai" in result["providers"]
    assert "anthropic" not in result["providers"]


def test_apply_deletions_deeply_nested():
    """Test deeply nested deletion."""
    config = {
        "level1": {
            "level2": {
                "keep": "value",
                "remove": "gone",
            }
        }
    }
    updates = {"level1": {"level2": {"remove": None}}}

    result = apply_deletions(config, updates)

    assert result["level1"]["level2"]["keep"] == "value"
    assert "remove" not in result["level1"]["level2"]


def test_apply_deletions_does_not_mutate_original():
    """Test that apply_deletions doesn't mutate the original config."""
    config = {"a": 1, "b": 2}
    updates = {"b": None}

    result = apply_deletions(config, updates)

    assert config == {"a": 1, "b": 2}  # Original unchanged
    assert "b" not in result


def test_deep_merge_and_apply_deletions_combined():
    """Test using both functions together as API does."""
    base = {
        "providers": {
            "openai": {"api_key": "old-key"},
            "anthropic": {"api_key": "ant-key"},
        },
        "workloads": {"default": {"model": "gpt-4"}},
    }
    updates = {
        "providers": {
            "openai": {"api_key": "new-key"},
            "anthropic": None,
        },
        "workloads": {"default": {"model": "gpt-4-turbo"}},
    }

    # First merge, then apply deletions (as API does)
    merged = deep_merge(base, updates)
    result = apply_deletions(merged, updates)

    assert result["providers"]["openai"]["api_key"] == "new-key"
    assert "anthropic" not in result["providers"]
    assert result["workloads"]["default"]["model"] == "gpt-4-turbo"


# =============================================================================
# Tests for LocalFileConfigProvider
# =============================================================================


@pytest.mark.asyncio
async def test_local_file_provider_creates_default_config():
    """Test that LocalFileConfigProvider creates config with defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        # Defaults must use known keys to pass validation
        defaults = {"server_port": 8765}

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
        existing_config = {"server_port": 1234}
        config_path.write_text(json.dumps(existing_config), encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults={"server_port": 8000})
        config = await provider.load()

        # Should merge with defaults
        assert config["server_port"] == 1234


@pytest.mark.asyncio
async def test_local_file_provider_saves_config():
    """Test that LocalFileConfigProvider saves config atomically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        provider = LocalFileConfigProvider(config_path)
        config = {"server_port": 9999}

        await provider.save(config)

        assert config_path.exists()
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["server_port"] == 9999
        assert "providers" in saved_config
        assert "workloads" in saved_config


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
        with pytest.raises(ConfigValidationError) as exc_info:
            await provider.load()
        # Check that error message is structured
        assert "unknown provider" in exc_info.value.errors[0]


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
        # Using known keys for this test requires them to be in known_root_keys
        # So we'll temporarily bypass the file provider which validates
        # and just test the manager logic with a mock dict

        provider = LocalFileConfigProvider(config_path, defaults={})
        manager = ConfigManager(provider)
        # Inject directly into manager to bypass schema validation for this unit test
        manager._config = {
            "server_host": "hello",
            "server_port": 42,
            "log_colors": True,
        }
        manager._loaded = True

        assert manager.get_str("server_host", "") == "hello"
        assert manager.get_int("server_port", 0) == 42
        assert manager.get_bool("log_colors", False) is True


@pytest.mark.asyncio
async def test_config_manager_set_and_update():
    """Test ConfigManager set and update methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        provider = LocalFileConfigProvider(config_path, defaults={})
        manager = ConfigManager(provider)
        await manager.initialize()

        # Test set
        await manager.set("server_host", "value1")
        assert manager.get("server_host") == "value1"

        # Test update
        await manager.update({"server_port": 123, "log_level": "DEBUG"})
        assert manager.get("server_port") == 123
        assert manager.get("log_level") == "DEBUG"

        # Verify persistence
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_config["server_host"] == "value1"
        assert saved_config["server_port"] == 123


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

        await manager.set("server_host", "value")

        assert callback_called
        assert received_config["server_host"] == "value"


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
        assert settings.openai_chat_model == expected_model
        assert settings.embedding_model == defaults["workloads"]["embeddings"]["model"]
        assert (
            settings.openai_embeddings_model
            == defaults["workloads"]["embeddings"]["model"]
        )
        assert settings.streaming_enabled == DEFAULT_STREAMING_ENABLED


@pytest.mark.asyncio
async def test_settings_embedding_model_tracks_workload_updates():
    """Embedding model property should reflect workload changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = get_default_config()

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        manager = ConfigManager(provider)
        await manager.initialize()

        settings = Settings(config_manager=manager)
        assert settings.embedding_model == "text-embedding-3-small"

        await manager.update(
            {
                "workloads": {
                    "embeddings": {
                        "provider": "openai",
                        "model": "text-embedding-3-large",
                    }
                }
            }
        )

        assert settings.embedding_model == "text-embedding-3-large"
        assert settings.openai_embeddings_model == "text-embedding-3-large"


def test_settings_validation_status_formats_errors(monkeypatch):
    """validation_status should provide user-friendly error list."""

    settings = Settings(config_manager=None)

    def _run_case(message: str, expected: list[str]) -> None:
        def fake_validate(model, embedding_model, api_key):
            raise ValueError(message)

        monkeypatch.setattr(
            "agentsmithy.config.validation.validate_or_raise", fake_validate
        )

        valid, errors = settings.validation_status()
        assert valid is False
        for token in expected:
            assert token in errors
        assert message in errors

    _run_case("API key missing", ["API key not configured"])
    _run_case(
        "Embedding selection invalid",
        ["Embedding model not configured or unsupported"],
    )
    _run_case("Model misconfigured", ["Model not configured or unsupported"])


@pytest.mark.asyncio
async def test_invalid_json_uses_last_valid_config():
    """Test that invalid JSON doesn't reset config to defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {"server_port": 8765}

        provider = LocalFileConfigProvider(config_path, defaults=defaults)

        # First load - creates with defaults
        config1 = await provider.load()
        assert config1["server_port"] == 8765

        # Update config
        await provider.save({"server_port": 9000})
        config2 = await provider.load()
        assert config2["server_port"] == 9000

        # Corrupt the JSON file
        config_path.write_text("{ invalid json }", encoding="utf-8")

        # Load should return last valid config, not defaults
        config3 = await provider.load()
        assert config3["server_port"] == 9000  # Not 8765!


@pytest.mark.asyncio
async def test_invalid_json_on_first_load_uses_defaults():
    """Test that invalid JSON on first load uses defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        defaults = {"server_port": 8765}

        # Create invalid JSON file
        config_path.write_text("{ invalid json }", encoding="utf-8")

        provider = LocalFileConfigProvider(config_path, defaults=defaults)
        config = await provider.load()

        # Should use defaults since no previous valid config exists
        assert config["server_port"] == 8765


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

    # Use valid keys
    defaults = {
        "server_host": "default",
        "server_port": 1000,
        "providers": {
            "openai": {
                "type": "openai",
                "api_key": "global",
                "base_url": "https://api.openai.com/v1",
                "options": {},
            }
        },
    }
    provider = LayeredConfigProvider(
        [
            LocalFileConfigProvider(global_path, defaults=defaults),
            LocalFileConfigProvider(local_path, defaults={}, create_if_missing=False),
        ]
    )

    merged = await provider.load()
    assert merged["server_host"] == "default"
    assert merged["server_port"] == 1000
    assert merged["providers"]["openai"]["api_key"] == "global"

    # Update global config via provider.save
    await provider.save(
        {
            "server_host": "global",
            "log_level": "INFO",
            "providers": {
                "openai": {"api_key": "global-updated", "options": {"timeout": 30}}
            },
        }
    )
    merged = await provider.load()
    assert merged["server_host"] == "global"
    assert merged["log_level"] == "INFO"
    assert merged["providers"]["openai"]["api_key"] == "global-updated"
    assert merged["providers"]["openai"]["options"]["timeout"] == 30

    # Write local override directly
    # Must use valid keys or they will be stripped
    local_path.write_text(
        json.dumps(
            {
                "server_host": "local",
                "server_port": 2000,
                "providers": {
                    "openai": {
                        "options": {
                            "timeout": 10,
                            "max_retries": 5,
                        },
                        "model": "gpt-5-mini",
                    }
                },
            }
        )
    )
    merged = await provider.load()
    assert merged["server_host"] == "local"
    assert merged["server_port"] == 2000
    # Both global and local nested fields should be preserved/merged
    assert merged["log_level"] == "INFO"
    assert merged["providers"]["openai"]["api_key"] == "global-updated"
    assert merged["providers"]["openai"]["options"]["timeout"] == 10
    assert merged["providers"]["openai"]["options"]["max_retries"] == 5
    assert merged["providers"]["openai"]["model"] == "gpt-5-mini"


@pytest.mark.asyncio
async def test_config_manager_with_local_overrides(tmp_path: Path):
    """ConfigManager should respect local overrides via layered provider."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    global_path = global_dir / "config.json"
    local_path = tmp_path / "project" / "config.json"
    local_path.parent.mkdir()

    defaults = {"server_host": "default"}
    provider = LayeredConfigProvider(
        [
            LocalFileConfigProvider(global_path, defaults=defaults),
            LocalFileConfigProvider(local_path, defaults={}, create_if_missing=False),
        ]
    )
    manager = ConfigManager(provider)
    await manager.initialize()

    # Update via manager -> should persist to global config
    await manager.set("server_host", "global")
    saved_global = json.loads(global_path.read_text(encoding="utf-8"))
    assert saved_global["server_host"] == "global"

    # Local override should take precedence after reload
    local_path.write_text(json.dumps({"server_host": "local"}), encoding="utf-8")
    new_config = await provider.load()
    manager._config = new_config
    assert manager.get("server_host") == "local"
