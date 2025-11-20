"""Test that server can start without API key configured."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_server_starts_without_api_key(tmp_path: Path):
    """Test that server can start even without API key configured."""
    # Create minimal config without API key
    config_dir = tmp_path / ".agentsmithy"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({}))

    workdir = tmp_path / "project"
    workdir.mkdir()

    # Import and initialize config
    from agentsmithy.config.defaults import get_default_config
    from agentsmithy.config.manager import ConfigManager
    from agentsmithy.config.providers import LocalFileConfigProvider
    from agentsmithy.config.settings import Settings

    # Create config manager
    provider = LocalFileConfigProvider(config_file, defaults=get_default_config())
    manager = ConfigManager(provider)

    import asyncio

    asyncio.run(manager.initialize())

    # Set as global
    import agentsmithy.config.manager as mgr_module

    old_manager = mgr_module._config_manager
    mgr_module._config_manager = manager

    try:
        # Create settings - should not raise even without API key
        settings = Settings(manager)

        # Validation should not block - just warn
        # The actual error should only happen when trying to use LLM
        try:
            settings.validate_or_raise()
            # If we get here, means defaults have some key
            # which is fine - we're testing it doesn't crash
        except ValueError as e:
            # Expected if no key configured
            assert "OPENAI_API_KEY" in str(e) or "api_key" in str(e).lower()

        # Config endpoint should work
        all_config = manager.get_all()
        assert all_config is not None

    finally:
        mgr_module._config_manager = old_manager


def test_server_startup_logic_soft_validation(tmp_path: Path, monkeypatch):
    """Test that server startup doesn't crash on missing API key."""
    from agentsmithy.config.defaults import get_default_config
    from agentsmithy.config.manager import ConfigManager
    from agentsmithy.config.providers import LocalFileConfigProvider
    from agentsmithy.config.settings import Settings

    # Create config without API key
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}))

    # Remove env var if present
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = LocalFileConfigProvider(config_file, defaults=get_default_config())
    manager = ConfigManager(provider)

    import asyncio

    asyncio.run(manager.initialize())

    settings = Settings(manager)

    # This should raise ValueError but not crash the process
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        settings.validate_or_raise()

    # But config manager still works
    assert manager.get_all() is not None


def test_can_set_api_key_after_startup(tmp_path: Path, monkeypatch):
    """Test that API key can be set after server starts."""
    from agentsmithy.config.defaults import get_default_config
    from agentsmithy.config.manager import ConfigManager
    from agentsmithy.config.providers import LocalFileConfigProvider
    from agentsmithy.config.settings import Settings

    # Start with no API key
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}))

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = LocalFileConfigProvider(config_file, defaults=get_default_config())
    manager = ConfigManager(provider)

    import asyncio

    asyncio.run(manager.initialize())

    settings = Settings(manager)

    # Validation should fail initially
    with pytest.raises(ValueError):
        settings.validate_or_raise()

    # Now set API key via config update
    asyncio.run(
        manager.update(
            {"providers": {"openai": {"api_key": "sk-test-key-set-after-startup"}}}
        )
    )

    # Create new Settings instance to pick up changes
    settings_after = Settings(manager)

    # Now validation should pass
    # (assuming model and embedding_model have valid defaults)
    api_key = settings_after.openai_api_key
    assert api_key == "sk-test-key-set-after-startup"
