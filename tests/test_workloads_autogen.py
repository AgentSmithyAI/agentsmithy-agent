"""Tests for workloads auto-generation and config merge behavior.

These tests verify:
1. Workloads are auto-generated from model catalog
2. Default config structure is correct
3. User config merges correctly with defaults (including edge cases)
4. New models/workloads are added to existing user configs
"""

import json
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from agentsmithy.config import (
    ConfigManager,
    LocalFileConfigProvider,
    get_default_config,
)
from agentsmithy.config.defaults import _build_default_workloads
from agentsmithy.config.schema import _build_model_catalog, deep_merge
from agentsmithy.llm.providers.ollama.catalog import OllamaModelCatalogProvider

# =============================================================================
# Tests for _build_default_workloads
# =============================================================================


class TestBuildDefaultWorkloads:
    """Tests for workloads auto-generation from model catalog."""

    def test_workloads_generated_from_chat_models(self):
        """Workloads should be generated for all chat models in catalog."""
        from agentsmithy.llm.providers.openai.models import SUPPORTED_OPENAI_CHAT_MODELS

        workloads = _build_default_workloads()

        for model in SUPPORTED_OPENAI_CHAT_MODELS:
            assert model in workloads, f"Missing workload for chat model: {model}"
            assert workloads[model]["model"] == model
            assert workloads[model]["provider"] == "openai"

    def test_workloads_generated_from_embedding_models(self):
        """Workloads should be generated for all embedding models in catalog."""
        from agentsmithy.llm.providers.openai.models import (
            SUPPORTED_OPENAI_EMBEDDING_MODELS,
        )

        workloads = _build_default_workloads()

        for model in SUPPORTED_OPENAI_EMBEDDING_MODELS:
            assert model in workloads, f"Missing workload for embedding model: {model}"
            assert workloads[model]["model"] == model
            assert workloads[model]["provider"] == "openai"

    def test_workloads_have_correct_structure(self):
        """Each workload should have provider, model, and options fields."""
        workloads = _build_default_workloads()

        for name, workload in workloads.items():
            assert "provider" in workload, f"Workload {name} missing 'provider'"
            assert "model" in workload, f"Workload {name} missing 'model'"
            assert "options" in workload, f"Workload {name} missing 'options'"
            assert isinstance(
                workload["options"], dict
            ), f"Workload {name} options should be dict"

    def test_workloads_include_models_with_dots_in_name(self):
        """Workloads for models with dots (e.g., gpt-5.1-codex) should be generated."""
        workloads = _build_default_workloads()

        # These models have dots in their names
        models_with_dots = [k for k in workloads.keys() if "." in k]
        assert len(models_with_dots) > 0, "Should have models with dots in names"

        # Verify they're properly structured
        for model in models_with_dots:
            assert workloads[model]["model"] == model

    def test_workloads_not_empty(self):
        """Generated workloads should not be empty."""
        workloads = _build_default_workloads()
        assert len(workloads) > 0, "Workloads should not be empty"


# =============================================================================
# Tests for get_default_config
# =============================================================================


class TestGetDefaultConfig:
    """Tests for default config generation."""

    def test_default_config_has_required_sections(self):
        """Default config should have all required top-level sections."""
        config = get_default_config()

        required_sections = [
            "providers",
            "workloads",
            "models",
            "server_host",
            "server_port",
        ]
        for section in required_sections:
            assert section in config, f"Missing required section: {section}"

    def test_default_config_workloads_match_generated(self):
        """Default config workloads should match _build_default_workloads output."""
        config = get_default_config()
        generated = _build_default_workloads()

        assert config["workloads"] == generated

    def test_default_config_models_reference_valid_workloads(self):
        """All model references should point to existing workloads."""
        config = get_default_config()
        available_workloads = set(config["workloads"].keys())

        # Check agents
        for agent_name, agent_config in config["models"]["agents"].items():
            workload = agent_config.get("workload")
            assert (
                workload in available_workloads
            ), f"Agent {agent_name} references unknown workload: {workload}"

        # Check embeddings
        embeddings_workload = config["models"]["embeddings"].get("workload")
        assert (
            embeddings_workload in available_workloads
        ), f"Embeddings references unknown workload: {embeddings_workload}"

        # Check summarization
        summarization_workload = config["models"]["summarization"].get("workload")
        assert (
            summarization_workload in available_workloads
        ), f"Summarization references unknown workload: {summarization_workload}"

    def test_default_config_has_openai_provider(self):
        """Default config should have openai provider configured."""
        config = get_default_config()

        assert "openai" in config["providers"]
        assert config["providers"]["openai"]["type"] == "openai"
        assert "api_key" in config["providers"]["openai"]
        assert "base_url" in config["providers"]["openai"]

    def test_default_config_universal_uses_strong_model(self):
        """Universal agent should use the strongest available model."""
        config = get_default_config()

        universal_workload = config["models"]["agents"]["universal"]["workload"]
        # Should be one of the top-tier models
        assert "codex" in universal_workload or "gpt-5" in universal_workload

    def test_default_config_inspector_uses_lighter_model(self):
        """Inspector agent should use a lighter model than universal."""
        config = get_default_config()

        inspector_workload = config["models"]["agents"]["inspector"]["workload"]
        # Should be a mini model
        assert "mini" in inspector_workload


# =============================================================================
# Tests for config merge behavior
# =============================================================================


class TestConfigMerge:
    """Tests for merging user config with defaults."""

    def test_user_workload_overrides_default(self):
        """User-defined workload should override default with same name."""
        defaults = get_default_config()
        user_config = {
            "workloads": {
                "gpt-5.1-codex": {
                    "provider": "openrouter",
                    "model": "openai/gpt-5.1-codex",
                    "options": {"custom": True},
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        # User config should override
        assert merged["workloads"]["gpt-5.1-codex"]["provider"] == "openrouter"
        assert merged["workloads"]["gpt-5.1-codex"]["model"] == "openai/gpt-5.1-codex"
        assert merged["workloads"]["gpt-5.1-codex"]["options"]["custom"] is True

    def test_new_default_workloads_added_to_user_config(self):
        """New workloads from defaults should be added to user config."""
        defaults = get_default_config()

        # User config without some workloads
        user_config = {
            "workloads": {
                "gpt-5.1-codex": {"provider": "openai", "model": "gpt-5.1-codex"}
            },
            "models": defaults["models"],
        }

        merged = deep_merge(defaults, user_config)

        # User's workload preserved
        assert "gpt-5.1-codex" in merged["workloads"]

        # Other workloads from defaults should be present
        for workload_name in defaults["workloads"]:
            assert (
                workload_name in merged["workloads"]
            ), f"Missing workload: {workload_name}"

    def test_user_model_assignment_preserved(self):
        """User's model-to-workload assignments should be preserved."""
        defaults = get_default_config()
        user_config = {
            "models": {
                "agents": {
                    "universal": {
                        "workload": "custom-workload"
                    },  # Different from default
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert merged["models"]["agents"]["universal"]["workload"] == "custom-workload"
        # Inspector should still have default
        assert (
            merged["models"]["agents"]["inspector"]["workload"]
            == defaults["models"]["agents"]["inspector"]["workload"]
        )

    def test_user_custom_workload_preserved(self):
        """User-defined custom workloads should be preserved."""
        defaults = get_default_config()
        user_config = {
            "workloads": {
                "my-custom-model": {
                    "provider": "ollama",
                    "model": "llama3:70b",
                    "options": {},
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert "my-custom-model" in merged["workloads"]
        assert merged["workloads"]["my-custom-model"]["provider"] == "ollama"

    def test_partial_workload_update_merges_correctly(self):
        """Partial update to workload should merge, not replace entirely."""
        defaults = get_default_config()
        user_config = {
            "workloads": {
                "gpt-5.1-codex": {
                    "options": {"temperature": 0.5}  # Only updating options
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        # Provider and model should come from defaults
        assert merged["workloads"]["gpt-5.1-codex"]["provider"] == "openai"
        assert merged["workloads"]["gpt-5.1-codex"]["model"] == "gpt-5.1-codex"
        # Options should be updated
        assert merged["workloads"]["gpt-5.1-codex"]["options"]["temperature"] == 0.5

    def test_empty_user_config_uses_all_defaults(self):
        """Empty user config should result in all defaults."""
        defaults = get_default_config()
        user_config = {}

        merged = deep_merge(defaults, user_config)

        assert merged == defaults

    def test_user_provider_override_preserved(self):
        """User's provider overrides should be preserved."""
        defaults = get_default_config()
        user_config = {
            "providers": {
                "openai": {
                    "api_key": "sk-user-key",
                    "base_url": "https://custom.openai.com/v1",
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert merged["providers"]["openai"]["api_key"] == "sk-user-key"
        assert (
            merged["providers"]["openai"]["base_url"] == "https://custom.openai.com/v1"
        )

    def test_user_adds_new_provider(self):
        """User can add new providers that don't exist in defaults."""
        defaults = get_default_config()
        user_config = {
            "providers": {
                "openrouter": {
                    "type": "openai",
                    "api_key": "sk-or-key",
                    "base_url": "https://openrouter.ai/api/v1",
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert "openrouter" in merged["providers"]
        assert "openai" in merged["providers"]  # Default preserved


# =============================================================================
# Integration tests with LocalFileConfigProvider
# =============================================================================


class TestConfigProviderMerge:
    """Integration tests for config provider merge behavior."""

    @pytest.mark.asyncio
    async def test_new_config_file_gets_all_defaults(self):
        """New config file should be created with all defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            defaults = get_default_config()

            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            config = await provider.load()

            # Should have all default workloads
            for workload_name in defaults["workloads"]:
                assert workload_name in config["workloads"]

    @pytest.mark.asyncio
    async def test_existing_config_gets_new_workloads(self):
        """Existing user config should get new workloads from updated defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Create old user config (missing some workloads)
            old_user_config = {
                "providers": {
                    "openai": {
                        "type": "openai",
                        "api_key": "sk-user-key",
                    }
                },
                "workloads": {
                    "gpt-5.1-codex": {
                        "provider": "openai",
                        "model": "gpt-5.1-codex",
                        "options": {},
                    }
                },
                "models": {
                    "agents": {
                        "universal": {"workload": "gpt-5.1-codex"},
                        "inspector": {"workload": "gpt-5.1-codex"},
                    },
                    "embeddings": {"workload": "text-embedding-3-small"},
                    "summarization": {"workload": "gpt-5.1-codex"},
                },
            }
            config_path.write_text(json.dumps(old_user_config))

            # Load with new defaults that have more workloads
            defaults = get_default_config()
            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            config = await provider.load()

            # User's api_key preserved
            assert config["providers"]["openai"]["api_key"] == "sk-user-key"

            # New workloads from defaults should be present
            assert "gpt-5.1" in config["workloads"]
            assert "text-embedding-3-large" in config["workloads"]

    @pytest.mark.asyncio
    async def test_user_workload_not_overwritten_by_defaults(self):
        """User's workload customizations should not be overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # User has customized a workload
            user_config = {
                "providers": {
                    "openai": {"type": "openai"},
                    "openrouter": {
                        "type": "openai",
                        "api_key": "sk-or-key",
                        "base_url": "https://openrouter.ai/api/v1",
                    },
                },
                "workloads": {
                    "gpt-5.1-codex": {
                        "provider": "openrouter",  # User switched provider
                        "model": "openai/gpt-5.1-codex",
                        "options": {"custom": True},
                    },
                    "text-embedding-3-small": {
                        "provider": "openai",
                        "model": "text-embedding-3-small",
                        "options": {},
                    },
                },
                "models": {
                    "agents": {
                        "universal": {"workload": "gpt-5.1-codex"},
                        "inspector": {"workload": "gpt-5.1-codex"},
                    },
                    "embeddings": {"workload": "text-embedding-3-small"},
                    "summarization": {"workload": "gpt-5.1-codex"},
                },
            }
            config_path.write_text(json.dumps(user_config))

            defaults = get_default_config()
            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            config = await provider.load()

            # User's customization preserved
            assert config["workloads"]["gpt-5.1-codex"]["provider"] == "openrouter"
            assert config["workloads"]["gpt-5.1-codex"]["options"]["custom"] is True

    @pytest.mark.asyncio
    async def test_config_manager_with_autogenerated_workloads(self):
        """ConfigManager should work correctly with auto-generated workloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            defaults = get_default_config()

            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            manager = ConfigManager(provider)
            await manager.initialize()

            # All workloads should be accessible
            workloads = manager.get("workloads")
            assert isinstance(workloads, dict)
            assert len(workloads) > 0

            # Models should reference valid workloads
            models = manager.get("models")
            universal_workload = models["agents"]["universal"]["workload"]
            assert universal_workload in workloads


# =============================================================================
# Edge cases and corner cases
# =============================================================================


class TestWorkloadsMergeEdgeCases:
    """Edge cases for workloads merge behavior."""

    def test_merge_with_none_values_preserves_defaults(self):
        """None values in user config should preserve defaults."""
        defaults = get_default_config()
        user_config = {"workloads": {"gpt-5.1-codex": None}}

        merged = deep_merge(defaults, user_config)

        # None means "don't touch", so default should be preserved
        assert (
            merged["workloads"]["gpt-5.1-codex"]
            == defaults["workloads"]["gpt-5.1-codex"]
        )

    def test_merge_deeply_nested_options(self):
        """Deep nesting in options should merge correctly."""
        defaults = get_default_config()
        user_config = {
            "workloads": {
                "gpt-5.1-codex": {
                    "options": {
                        "nested": {"deep": {"value": 42}},
                    }
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert (
            merged["workloads"]["gpt-5.1-codex"]["options"]["nested"]["deep"]["value"]
            == 42
        )

    def test_user_config_with_extra_fields_preserved(self):
        """Extra fields in user config should be preserved."""
        defaults = get_default_config()
        user_config = {
            "workloads": {
                "gpt-5.1-codex": {
                    "provider": "openai",
                    "model": "gpt-5.1-codex",
                    "options": {},
                    "custom_field": "user_data",  # Extra field
                }
            }
        }

        merged = deep_merge(defaults, user_config)

        assert merged["workloads"]["gpt-5.1-codex"]["custom_field"] == "user_data"

    def test_workload_with_dots_in_name_works(self):
        """Workloads with dots in name should work correctly."""
        defaults = get_default_config()

        # Verify gpt-5.1-codex exists and works
        assert "gpt-5.1-codex" in defaults["workloads"]
        assert defaults["workloads"]["gpt-5.1-codex"]["model"] == "gpt-5.1-codex"

    def test_models_reference_workload_with_dots(self):
        """Models section should correctly reference workloads with dots."""
        defaults = get_default_config()

        universal_workload = defaults["models"]["agents"]["universal"]["workload"]
        # Should be able to find this workload
        assert universal_workload in defaults["workloads"]

    @pytest.mark.asyncio
    async def test_corrupt_user_workload_rejected_by_validation(self):
        """If user workload is not a dict, validation should reject it."""
        from agentsmithy.config import ConfigValidationError

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Corrupt workload (string instead of dict)
            user_config = {
                "providers": {"openai": {"type": "openai"}},
                "workloads": {
                    "gpt-5.1-codex": "corrupted",  # Invalid - should be dict
                    "text-embedding-3-small": {
                        "provider": "openai",
                        "model": "text-embedding-3-small",
                        "options": {},
                    },
                },
                "models": {
                    "agents": {
                        "universal": {"workload": "gpt-5.1-codex"},
                        "inspector": {"workload": "gpt-5.1-codex"},
                    },
                    "embeddings": {"workload": "text-embedding-3-small"},
                    "summarization": {"workload": "gpt-5.1-codex"},
                },
            }
            config_path.write_text(json.dumps(user_config))

            defaults = get_default_config()
            provider = LocalFileConfigProvider(config_path, defaults=defaults)

            # Validation should reject corrupted workload
            with pytest.raises(ConfigValidationError) as exc_info:
                await provider.load()

            assert "gpt-5.1-codex" in str(exc_info.value)

    def test_empty_workloads_in_user_gets_defaults(self):
        """Empty workloads dict in user config should get all defaults."""
        defaults = get_default_config()
        user_config = {"workloads": {}}

        merged = deep_merge(defaults, user_config)

        # All default workloads should be present
        assert merged["workloads"] == defaults["workloads"]

    def test_user_removes_workload_but_models_still_reference_it(self):
        """Test behavior when user removes a workload that's still referenced."""
        # This is a validation concern, not merge concern
        # The merge will work, but validation should catch it
        defaults = get_default_config()

        # This is valid from merge perspective
        user_config = deepcopy(defaults)
        del user_config["workloads"]["gpt-5.1-codex"]
        # But models still reference it - this should be caught by validation

        merged = deep_merge(defaults, user_config)
        # gpt-5.1-codex should NOT be in merged (user removed it... wait, no)
        # Actually deep_merge doesn't support deletions, only additions/overwrites
        # So the default workload will still be there
        assert "gpt-5.1-codex" in merged["workloads"]


class TestSettingsWithAutoGeneratedWorkloads:
    """Test Settings class works with auto-generated workloads."""

    @pytest.mark.asyncio
    async def test_settings_model_resolves_through_workload(self):
        """Settings.model should resolve through workload chain."""
        from agentsmithy.config.settings import Settings

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            defaults = get_default_config()

            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            manager = ConfigManager(provider)
            await manager.initialize()

            settings = Settings(config_manager=manager)

            # Should resolve to the model from the workload
            assert settings.model is not None
            expected_workload = defaults["models"]["agents"]["universal"]["workload"]
            expected_model = defaults["workloads"][expected_workload]["model"]
            assert settings.model == expected_model

    @pytest.mark.asyncio
    async def test_settings_embedding_model_resolves_through_workload(self):
        """Settings.embedding_model should resolve through workload chain."""
        from agentsmithy.config.settings import Settings

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            defaults = get_default_config()

            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            manager = ConfigManager(provider)
            await manager.initialize()

            settings = Settings(config_manager=manager)

            # Should resolve to the model from the workload
            assert settings.embedding_model is not None
            expected_workload = defaults["models"]["embeddings"]["workload"]
            expected_model = defaults["workloads"][expected_workload]["model"]
            assert settings.embedding_model == expected_model

    @pytest.mark.asyncio
    async def test_settings_with_workload_containing_dots(self):
        """Settings should work with workload names containing dots."""
        from agentsmithy.config.settings import Settings

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            defaults = get_default_config()

            # Ensure we're testing with a workload that has dots
            assert "." in defaults["models"]["agents"]["universal"]["workload"]

            provider = LocalFileConfigProvider(config_path, defaults=defaults)
            manager = ConfigManager(provider)
            await manager.initialize()

            settings = Settings(config_manager=manager)

            # Should correctly resolve despite dots in name
            assert settings.model == "gpt-5.1-codex"


# =============================================================================
# Tests for Ollama dynamic model catalog
# =============================================================================


class TestOllamaModelCatalog:
    """Tests for dynamic Ollama model fetching via catalog provider."""

    def test_ollama_catalog_returns_empty_without_base_url(self):
        """Should return empty catalog when no base_url configured."""
        provider = OllamaModelCatalogProvider()
        catalog = provider.get_catalog({})
        assert catalog.is_empty()

    def test_ollama_catalog_returns_empty_on_connection_error(self):
        """Should return empty catalog when Ollama server is not reachable."""
        provider = OllamaModelCatalogProvider()
        catalog = provider.get_catalog(
            {"base_url": "http://localhost:99999/v1"}  # Invalid port
        )
        assert catalog.is_empty()

    def test_ollama_catalog_handles_v1_suffix_in_url(self):
        """Should strip /v1 suffix to reach /api/tags endpoint."""
        provider = OllamaModelCatalogProvider()
        # Should not crash, just return empty
        catalog = provider.get_catalog({"base_url": "http://invalid-host:11434/v1"})
        assert catalog.is_empty()

    def test_model_catalog_includes_openai(self):
        """model_catalog should always include OpenAI models."""
        catalog = _build_model_catalog({})
        assert "openai" in catalog
        assert "chat" in catalog["openai"]
        assert len(catalog["openai"]["chat"]) > 0

    def test_model_catalog_includes_ollama_when_configured(self):
        """model_catalog should include Ollama section when provider exists."""
        # Note: This will only have models if Ollama is actually running
        providers = {
            "ollama": {
                "type": "ollama",
                "base_url": "http://localhost:11434/v1",
            }
        }
        catalog = _build_model_catalog(providers)

        # OpenAI should always be there
        assert "openai" in catalog

        # Ollama section exists only if server responded with models
        # (may or may not be present depending on test environment)
        if "ollama" in catalog:
            assert "chat" in catalog["ollama"]
            assert isinstance(catalog["ollama"]["chat"], list)


# =============================================================================
# Tests for workload kind auto-detection
# =============================================================================


class TestWorkloadKindAutoDetection:
    """Tests for workload kind (chat/embeddings) auto-detection."""

    def test_chat_model_detected_as_chat(self):
        """Chat models should be detected as kind='chat'."""
        from agentsmithy.llm.providers.known_models import infer_workload_kind

        assert infer_workload_kind("gpt-5.1-codex") == "chat"
        assert infer_workload_kind("gpt-4.1") == "chat"
        assert infer_workload_kind("llama3:70b") == "chat"

    def test_embedding_model_detected_as_embeddings(self):
        """Embedding models should be detected as kind='embeddings'."""
        from agentsmithy.llm.providers.known_models import infer_workload_kind

        assert infer_workload_kind("text-embedding-3-small") == "embeddings"
        assert infer_workload_kind("text-embedding-3-large") == "embeddings"
        assert infer_workload_kind("nomic-embed-text") == "embeddings"

    def test_unknown_model_defaults_to_chat(self):
        """Unknown models should default to kind='chat'."""
        from agentsmithy.llm.providers.known_models import infer_workload_kind

        assert infer_workload_kind("some-unknown-model") == "chat"
        assert infer_workload_kind("custom-model:latest") == "chat"

    def test_none_model_defaults_to_chat(self):
        """None/empty model should default to kind='chat'."""
        from agentsmithy.llm.providers.known_models import infer_workload_kind

        assert infer_workload_kind(None) == "chat"
        assert infer_workload_kind("") == "chat"

    def test_vendor_specific_detection(self):
        """Detection should work with vendor hint."""
        from agentsmithy.llm.providers.known_models import infer_workload_kind
        from agentsmithy.llm.providers.types import Vendor

        # OpenAI embedding
        assert (
            infer_workload_kind("text-embedding-3-small", Vendor.OPENAI) == "embeddings"
        )
        # Ollama embedding
        assert infer_workload_kind("nomic-embed-text", Vendor.OLLAMA) == "embeddings"
        # String vendor also works
        assert infer_workload_kind("text-embedding-3-large", "openai") == "embeddings"

    def test_metadata_includes_kind_for_workloads(self):
        """build_config_metadata should include kind for each workload."""
        from agentsmithy.config.schema import build_config_metadata

        config = get_default_config()
        metadata = build_config_metadata(config)

        workloads = metadata["workloads"]
        assert len(workloads) > 0

        # All workloads should have kind
        for wl in workloads:
            assert "kind" in wl, f"Workload {wl['name']} missing kind"
            assert wl["kind"] in ("chat", "embeddings")

    def test_chat_workloads_have_chat_kind(self):
        """Chat model workloads should have kind='chat'."""
        from agentsmithy.config.schema import build_config_metadata

        config = get_default_config()
        metadata = build_config_metadata(config)

        chat_workloads = [
            wl for wl in metadata["workloads"] if wl["name"] == "gpt-5.1-codex"
        ]
        assert len(chat_workloads) == 1
        assert chat_workloads[0]["kind"] == "chat"

    def test_embedding_workloads_have_embeddings_kind(self):
        """Embedding model workloads should have kind='embeddings'."""
        from agentsmithy.config.schema import build_config_metadata

        config = get_default_config()
        metadata = build_config_metadata(config)

        emb_workloads = [
            wl for wl in metadata["workloads"] if wl["name"] == "text-embedding-3-small"
        ]
        assert len(emb_workloads) == 1
        assert emb_workloads[0]["kind"] == "embeddings"

    def test_explicit_kind_overrides_auto_detection(self):
        """Explicit kind in workload config should override auto-detection."""
        from agentsmithy.config.schema import build_config_metadata

        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {
                # Force chat model to be treated as embeddings
                "gpt-5.1-codex": {
                    "provider": "openai",
                    "model": "gpt-5.1-codex",
                    "kind": "embeddings",  # Explicit override
                }
            },
            "models": {},
        }
        metadata = build_config_metadata(config)

        wl = next(w for w in metadata["workloads"] if w["name"] == "gpt-5.1-codex")
        assert wl["kind"] == "embeddings"  # Explicit value used, not auto-detected

    def test_null_kind_triggers_auto_detection(self):
        """Null kind should trigger auto-detection."""
        from agentsmithy.config.schema import build_config_metadata

        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {
                "text-embedding-3-small": {
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                    "kind": None,  # Explicitly null = auto-detect
                }
            },
            "models": {},
        }
        metadata = build_config_metadata(config)

        wl = next(
            w for w in metadata["workloads"] if w["name"] == "text-embedding-3-small"
        )
        assert wl["kind"] == "embeddings"  # Auto-detected from model name

    def test_missing_kind_triggers_auto_detection(self):
        """Missing kind field should trigger auto-detection."""
        from agentsmithy.config.schema import build_config_metadata

        config = {
            "providers": {"openai": {"type": "openai"}},
            "workloads": {
                "text-embedding-3-large": {
                    "provider": "openai",
                    "model": "text-embedding-3-large",
                    # kind not specified at all
                }
            },
            "models": {},
        }
        metadata = build_config_metadata(config)

        wl = next(
            w for w in metadata["workloads"] if w["name"] == "text-embedding-3-large"
        )
        assert wl["kind"] == "embeddings"  # Auto-detected from model name


# =============================================================================
# Tests for workload_kinds in metadata
# =============================================================================


class TestWorkloadKindsMetadata:
    """Tests for workload_kinds enum values in metadata."""

    def test_workload_kinds_in_metadata(self):
        """Metadata should include workload_kinds with possible values."""
        from agentsmithy.config.schema import build_config_metadata

        config = get_default_config()
        metadata = build_config_metadata(config)

        assert "workload_kinds" in metadata
        assert metadata["workload_kinds"] == ["chat", "embeddings"]

    def test_workload_kinds_matches_enum(self):
        """workload_kinds should match WorkloadKind enum values."""
        from agentsmithy.config.schema import build_config_metadata
        from agentsmithy.llm.providers.types import WorkloadKind

        config = get_default_config()
        metadata = build_config_metadata(config)

        expected = [k.value for k in WorkloadKind]
        assert metadata["workload_kinds"] == expected

    def test_all_workloads_have_valid_kind(self):
        """All workloads should have kind from workload_kinds."""
        from agentsmithy.config.schema import build_config_metadata

        config = get_default_config()
        metadata = build_config_metadata(config)

        valid_kinds = set(metadata["workload_kinds"])
        for wl in metadata["workloads"]:
            assert wl["kind"] in valid_kinds, f"Workload {wl['name']} has invalid kind"


# =============================================================================
# Tests for explicit kind in default workloads
# =============================================================================


class TestDefaultWorkloadsExplicitKind:
    """Tests that default workloads have explicit kind set (not null)."""

    def test_default_chat_workloads_have_explicit_kind(self):
        """Default chat workloads should have kind='chat' explicitly set."""
        config = get_default_config()
        workloads = config["workloads"]

        # Check a known chat model
        assert "gpt-5.1-codex" in workloads
        assert workloads["gpt-5.1-codex"]["kind"] == "chat"

    def test_default_embedding_workloads_have_explicit_kind(self):
        """Default embedding workloads should have kind='embeddings' explicitly set."""
        config = get_default_config()
        workloads = config["workloads"]

        # Check a known embedding model
        assert "text-embedding-3-small" in workloads
        assert workloads["text-embedding-3-small"]["kind"] == "embeddings"

    def test_all_default_workloads_have_explicit_kind(self):
        """All default workloads should have kind explicitly set (not null)."""
        config = get_default_config()
        workloads = config["workloads"]

        for name, wl in workloads.items():
            assert "kind" in wl, f"Workload {name} missing 'kind' field"
            assert wl["kind"] is not None, f"Workload {name} has null 'kind'"
            assert wl["kind"] in (
                "chat",
                "embeddings",
            ), f"Workload {name} has invalid kind"

    def test_default_workloads_kind_not_null_in_config(self):
        """Verify kind is NOT null in raw default config (regression test)."""
        config = get_default_config()
        workloads = config["workloads"]

        # Explicitly check that kind is string, not None
        for name, wl in workloads.items():
            kind_value = wl.get("kind")
            assert isinstance(
                kind_value, str
            ), f"Workload {name} kind should be string, got {type(kind_value)}"


# =============================================================================
# Tests for model validation removal (regression)
# =============================================================================


class TestModelValidationRemoved:
    """Regression tests: any model should be allowed, no validation errors."""

    def test_custom_model_allowed_in_validation(self):
        """validate_or_raise should NOT reject unknown models."""
        from agentsmithy.config.validation import validate_or_raise

        # This should NOT raise - any model is allowed
        validate_or_raise(
            model="gpt-3.5-turbo",  # Not in SUPPORTED list
            embedding_model="text-embedding-3-small",
            api_key="sk-test-key",
        )

    def test_completely_custom_model_allowed(self):
        """Completely custom model names should be allowed."""
        from agentsmithy.config.validation import validate_or_raise

        validate_or_raise(
            model="my-custom-finetuned-model",
            embedding_model="custom-embedding-model",
            api_key="sk-test-key",
        )

    def test_openrouter_model_allowed(self):
        """OpenRouter-style model paths should be allowed."""
        from agentsmithy.config.validation import validate_or_raise

        validate_or_raise(
            model="anthropic/claude-3-opus",
            embedding_model="openai/text-embedding-3-large",
            api_key="sk-test-key",
        )

    def test_ollama_model_allowed(self):
        """Ollama model names should be allowed."""
        from agentsmithy.config.validation import validate_or_raise

        validate_or_raise(
            model="llama3:70b",
            embedding_model="nomic-embed-text:latest",
            api_key="sk-test-key",
        )

    def test_empty_model_still_requires_api_key(self, monkeypatch):
        """Even with no model validation, API key is still required."""
        from agentsmithy.config.validation import validate_or_raise

        # Clear env var to ensure test works regardless of environment
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError) as exc_info:
            validate_or_raise(
                model="any-model",
                embedding_model="any-embedding",
                api_key=None,
            )
        assert "OPENAI_API_KEY is required" in str(exc_info.value)


# =============================================================================
# Tests for OpenAI dynamic catalog (with mocks)
# =============================================================================


class TestOpenAIDynamicCatalog:
    """Tests for OpenAI catalog fetching from API."""

    def test_catalog_fetches_from_api_when_key_provided(self):
        """Should fetch models from OpenAI API when api_key is provided."""
        from unittest.mock import MagicMock, patch

        from agentsmithy.llm.providers.openai.catalog import OpenAIModelCatalogProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4-turbo"},
                {"id": "text-embedding-3-small"},
            ]
        }

        provider = OpenAIModelCatalogProvider()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            catalog = provider.get_catalog(
                {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}
            )

        assert "gpt-4o" in catalog.chat
        assert "gpt-4-turbo" in catalog.chat
        assert "text-embedding-3-small" in catalog.embeddings

    def test_catalog_falls_back_to_static_on_api_error(self):
        """Should fall back to static catalog when API fails."""
        from unittest.mock import patch

        from agentsmithy.llm.providers.openai.catalog import OpenAIModelCatalogProvider

        provider = OpenAIModelCatalogProvider()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception(
                "Network error"
            )

            catalog = provider.get_catalog(
                {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}
            )

        # Should have static models as fallback
        assert len(catalog.chat) > 0
        assert "gpt-5.1-codex" in catalog.chat  # From static registry

    def test_catalog_uses_static_when_no_api_key(self):
        """Should use static catalog when no api_key provided."""
        from agentsmithy.llm.providers.openai.catalog import OpenAIModelCatalogProvider

        provider = OpenAIModelCatalogProvider()
        catalog = provider.get_catalog({})  # No api_key

        # Should have static models
        assert len(catalog.chat) > 0
        assert "gpt-5.1-codex" in catalog.chat

    def test_catalog_filters_out_excluded_models(self):
        """Should exclude fine-tuned, audio, image models."""
        from unittest.mock import MagicMock, patch

        from agentsmithy.llm.providers.openai.catalog import OpenAIModelCatalogProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "ft:gpt-4:my-org:custom:id"},  # fine-tuned - exclude
                {"id": "whisper-1"},  # audio - exclude
                {"id": "dall-e-3"},  # image - exclude
                {"id": "tts-1"},  # text-to-speech - exclude
                {"id": "davinci-002"},  # old completions - exclude
            ]
        }

        provider = OpenAIModelCatalogProvider()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            catalog = provider.get_catalog(
                {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}
            )

        assert "gpt-4o" in catalog.chat
        assert "ft:gpt-4:my-org:custom:id" not in catalog.chat
        assert "whisper-1" not in catalog.chat
        assert "dall-e-3" not in catalog.chat
        assert "tts-1" not in catalog.chat
        assert "davinci-002" not in catalog.chat


# =============================================================================
# Tests for workload lookup with dots in names (regression)
# =============================================================================


class TestWorkloadLookupWithDots:
    """Regression tests for workload names containing dots (e.g., gpt-5.1-codex)."""

    def test_get_workload_config_handles_dots(self):
        """_get_workload_config should handle workload names with dots."""
        from unittest.mock import MagicMock

        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {
            "workloads": {
                "gpt-5.1-codex": {
                    "provider": "openai",
                    "model": "gpt-5.1-codex",
                }
            }
        }

        settings = Settings(config_manager=mock_manager)
        config = settings._get_workload_config("gpt-5.1-codex")

        assert config is not None
        assert config["provider"] == "openai"
        assert config["model"] == "gpt-5.1-codex"

    def test_get_workload_config_multiple_dots(self):
        """Should handle workload names with multiple dots."""
        from unittest.mock import MagicMock

        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {
            "workloads": {
                "openai/gpt-4.1.preview": {
                    "provider": "openrouter",
                    "model": "openai/gpt-4.1.preview",
                }
            }
        }

        settings = Settings(config_manager=mock_manager)
        config = settings._get_workload_config("openai/gpt-4.1.preview")

        assert config is not None
        assert config["model"] == "openai/gpt-4.1.preview"

    def test_provider_finds_workload_with_dots(self):
        """OpenAIProvider should find workloads with dots in name."""
        from unittest.mock import MagicMock, patch

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.agents":
                return {"universal": {"workload": "gpt-5.1-codex"}}
            if key == "providers.openai":
                return {"api_key": "sk-xxx", "type": "openai"}
            return default

        mock_settings._get.side_effect = mock_get
        mock_settings._get_workload_config.return_value = {
            "provider": "openai",
            "model": "gpt-5.1-codex",
        }

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with patch(
                "agentsmithy.llm.providers.openai.provider.register_builtin_adapters"
            ):
                with patch(
                    "agentsmithy.llm.providers.openai.provider.get_adapter"
                ) as mock_adapter:
                    mock_adapter.return_value.build_langchain.return_value = (
                        "langchain_openai.ChatOpenAI",
                        {},
                    )
                    with patch(
                        "agentsmithy.llm.providers.openai.provider.import_module"
                    ) as mock_import:
                        mock_import.return_value.ChatOpenAI = MagicMock()

                        from agentsmithy.llm.providers.openai.provider import (
                            OpenAIProvider,
                        )

                        provider = OpenAIProvider()

                        # Should successfully find the workload
                        assert provider.model == "gpt-5.1-codex"

    def test_embeddings_provider_finds_workload_with_dots(self):
        """OpenAIEmbeddingsProvider should find workloads with dots."""
        from unittest.mock import MagicMock, patch

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "text-embedding-3.5-large"}
            if key == "providers.openai":
                return {"api_key": "sk-xxx"}
            return default

        mock_settings._get.side_effect = mock_get
        mock_settings._get_workload_config.return_value = {
            "provider": "openai",
            "model": "text-embedding-3.5-large",
        }

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            from agentsmithy.llm.providers.openai.provider_embeddings import (
                OpenAIEmbeddingsProvider,
            )

            provider = OpenAIEmbeddingsProvider()

            assert provider.model == "text-embedding-3.5-large"
