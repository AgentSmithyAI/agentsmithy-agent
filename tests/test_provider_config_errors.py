"""Tests for OpenAI provider configuration error handling.

These tests verify that OpenAIProvider and OpenAIEmbeddingsProvider
raise clear, actionable errors when configuration is incomplete or invalid.
This ensures fail-fast behavior instead of silent fallbacks.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOpenAIProviderConfigErrors:
    """Test OpenAIProvider raises appropriate errors for invalid configurations."""

    def test_missing_models_agents_config_raises_error(self):
        """
        When models.agents configuration is completely missing,
        OpenAIProvider should raise ValueError with clear message
        telling user to check models.agents in config.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()
        mock_settings._get.return_value = None  # models.agents not found

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "models.agents configuration not found" in str(exc_info.value)
            assert "Check models.agents in your config" in str(exc_info.value)

    def test_missing_agent_entry_raises_error(self):
        """
        When specific agent (e.g., 'universal') is not found in models.agents,
        OpenAIProvider should raise ValueError with agent name in message.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()
        mock_settings._get.side_effect = lambda key, default: (
            {} if key == "models.agents" else default  # agents config exists but empty
        )

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "Agent configuration not found for 'universal'" in str(
                exc_info.value
            )

    def test_missing_workload_in_agent_raises_error(self):
        """
        When agent exists but has no 'workload' key specified,
        OpenAIProvider should raise ValueError telling user to set workload.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()
        mock_settings._get.side_effect = lambda key, default: (
            {"universal": {}}  # agent exists but no workload
            if key == "models.agents"
            else default
        )

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "has no workload specified" in str(exc_info.value)
            assert "models.agents.universal.workload" in str(exc_info.value)

    def test_missing_workload_definition_raises_error(self):
        """
        When agent references a workload that doesn't exist in workloads config,
        OpenAIProvider should raise ValueError with workload name.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.agents":
                return {"universal": {"workload": "nonexistent"}}
            if key == "workloads.nonexistent":
                return None  # workload not found
            return default

        mock_settings._get.side_effect = mock_get

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "Workload 'nonexistent' not found" in str(exc_info.value)
            assert "workloads.nonexistent" in str(exc_info.value)

    def test_missing_provider_in_workload_raises_error(self):
        """
        When workload exists but has no 'provider' key,
        OpenAIProvider should raise ValueError telling user to set provider.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.agents":
                return {"universal": {"workload": "reasoning"}}
            if key == "workloads.reasoning":
                return {"model": "gpt-4"}  # no provider key
            return default

        mock_settings._get.side_effect = mock_get

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "has no provider specified" in str(exc_info.value)
            assert "workloads.reasoning.provider" in str(exc_info.value)

    def test_missing_provider_definition_raises_error(self):
        """
        When workload references a provider that doesn't exist in providers config,
        OpenAIProvider should raise ValueError with provider name.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.agents":
                return {"universal": {"workload": "reasoning"}}
            if key == "workloads.reasoning":
                return {"provider": "nonexistent", "model": "gpt-4"}
            if key == "providers.nonexistent":
                return None  # provider not found
            return default

        mock_settings._get.side_effect = mock_get

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "Provider 'nonexistent' not found" in str(exc_info.value)
            assert "providers.nonexistent" in str(exc_info.value)

    def test_missing_model_raises_error(self):
        """
        When neither workload nor provider specifies a model,
        OpenAIProvider should raise ValueError about missing model.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.agents":
                return {"universal": {"workload": "reasoning"}}
            if key == "workloads.reasoning":
                return {"provider": "openai"}  # no model
            if key == "providers.openai":
                return {"api_key": "sk-xxx"}  # no model here either
            return default

        mock_settings._get.side_effect = mock_get

        with patch("agentsmithy.llm.providers.openai.provider.settings", mock_settings):
            with pytest.raises(ValueError) as exc_info:
                OpenAIProvider()

            assert "LLM model not specified" in str(exc_info.value)

    def test_summarization_agent_uses_models_summarization(self):
        """
        When agent_name='summarization', OpenAIProvider should read config
        from models.summarization instead of models.agents.
        """
        from agentsmithy.llm.providers.openai.provider import OpenAIProvider

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.summarization":
                return {"workload": "summarization"}
            if key == "workloads.summarization":
                return {"provider": "openai", "model": "gpt-4"}
            if key == "providers.openai":
                return {"api_key": "sk-xxx"}
            return default

        mock_settings._get.side_effect = mock_get

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

                        provider = OpenAIProvider(agent_name="summarization")

                        assert provider.model == "gpt-4"
                        # Verify models.summarization was accessed
                        mock_settings._get.assert_any_call("models.summarization", None)


class TestOpenAIEmbeddingsProviderConfigErrors:
    """Test OpenAIEmbeddingsProvider raises appropriate errors for invalid configurations."""

    def test_missing_embeddings_config_raises_error(self):
        """
        When models.embeddings configuration is missing,
        OpenAIEmbeddingsProvider should raise ValueError with clear message.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()
        mock_settings._get.return_value = None

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "Embeddings configuration not found" in str(exc_info.value)
            assert "models.embeddings" in str(exc_info.value)

    def test_missing_workload_in_embeddings_raises_error(self):
        """
        When models.embeddings exists but has no workload,
        OpenAIEmbeddingsProvider should raise ValueError.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()
        mock_settings._get.side_effect = lambda key, default: (
            {}  # embeddings config exists but no workload
            if key == "models.embeddings"
            else default
        )

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "no workload specified" in str(exc_info.value)

    def test_missing_workload_definition_raises_error(self):
        """
        When embeddings references a workload that doesn't exist,
        OpenAIEmbeddingsProvider should raise ValueError.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "nonexistent"}
            if key == "workloads.nonexistent":
                return None
            return default

        mock_settings._get.side_effect = mock_get

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "Workload 'nonexistent' not found" in str(exc_info.value)

    def test_missing_provider_in_workload_raises_error(self):
        """
        When embeddings workload has no provider specified,
        OpenAIEmbeddingsProvider should raise ValueError.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "embeddings"}
            if key == "workloads.embeddings":
                return {"model": "text-embedding-3-small"}  # no provider
            return default

        mock_settings._get.side_effect = mock_get

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "has no provider specified" in str(exc_info.value)

    def test_missing_provider_definition_raises_error(self):
        """
        When embeddings workload references non-existent provider,
        OpenAIEmbeddingsProvider should raise ValueError.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "embeddings"}
            if key == "workloads.embeddings":
                return {"provider": "nonexistent", "model": "text-embedding-3-small"}
            if key == "providers.nonexistent":
                return None
            return default

        mock_settings._get.side_effect = mock_get

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "Provider 'nonexistent' not found" in str(exc_info.value)

    def test_missing_model_raises_error(self):
        """
        When neither workload nor provider specifies embeddings model,
        OpenAIEmbeddingsProvider should raise ValueError.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "embeddings"}
            if key == "workloads.embeddings":
                return {"provider": "openai"}  # no model
            if key == "providers.openai":
                return {"api_key": "sk-xxx"}  # no model here either
            return default

        mock_settings._get.side_effect = mock_get

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            with pytest.raises(ValueError) as exc_info:
                OpenAIEmbeddingsProvider()

            assert "Embeddings model not specified" in str(exc_info.value)

    def test_explicit_model_overrides_config(self):
        """
        When model is passed explicitly to constructor,
        it should override the model from configuration.
        """
        from agentsmithy.llm.providers.openai.provider_embeddings import (
            OpenAIEmbeddingsProvider,
        )

        mock_settings = MagicMock()

        def mock_get(key, default):
            if key == "models.embeddings":
                return {"workload": "embeddings"}
            if key == "workloads.embeddings":
                return {"provider": "openai", "model": "text-embedding-3-small"}
            if key == "providers.openai":
                return {"api_key": "sk-xxx"}
            return default

        mock_settings._get.side_effect = mock_get

        with patch(
            "agentsmithy.llm.providers.openai.provider_embeddings.settings",
            mock_settings,
        ):
            provider = OpenAIEmbeddingsProvider(model="text-embedding-3-large")
            assert provider.model == "text-embedding-3-large"


class TestSettingsModelResolution:
    """Test Settings.model and Settings.embedding_model property resolution."""

    def test_model_returns_none_when_agents_not_dict(self):
        """
        When models.agents is not a dict (e.g., None or wrong type),
        Settings.model should return None instead of crashing.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {"models": {"agents": None}}

        settings = Settings(config_manager=mock_manager)
        assert settings.model is None

    def test_model_returns_none_when_universal_not_dict(self):
        """
        When models.agents.universal is not a dict,
        Settings.model should return None.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {"models": {"agents": {"universal": None}}}

        settings = Settings(config_manager=mock_manager)
        assert settings.model is None

    def test_model_returns_none_when_no_workload(self):
        """
        When models.agents.universal has no workload key,
        Settings.model should return None.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {"models": {"agents": {"universal": {}}}}

        settings = Settings(config_manager=mock_manager)
        assert settings.model is None

    def test_model_returns_none_when_workload_config_missing(self):
        """
        When workload referenced by agent doesn't exist,
        Settings.model should return None.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {
            "models": {"agents": {"universal": {"workload": "nonexistent"}}},
            "workloads": {},
        }

        settings = Settings(config_manager=mock_manager)
        assert settings.model is None

    def test_model_returns_value_from_workload(self):
        """
        When full config chain exists,
        Settings.model should return model from workload config.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {
            "models": {"agents": {"universal": {"workload": "reasoning"}}},
            "workloads": {"reasoning": {"model": "gpt-5"}},
        }

        settings = Settings(config_manager=mock_manager)
        assert settings.model == "gpt-5"

    def test_embedding_model_returns_none_when_embeddings_not_dict(self):
        """
        When models.embeddings is not a dict,
        Settings.embedding_model should return None.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {"models": {"embeddings": None}}

        settings = Settings(config_manager=mock_manager)
        assert settings.embedding_model is None

    def test_embedding_model_returns_value_from_workload(self):
        """
        When full config chain exists for embeddings,
        Settings.embedding_model should return model from workload.
        """
        from agentsmithy.config.settings import Settings

        mock_manager = MagicMock()
        mock_manager.get_all.return_value = {
            "models": {"embeddings": {"workload": "embeddings"}},
            "workloads": {"embeddings": {"model": "text-embedding-3-large"}},
        }

        settings = Settings(config_manager=mock_manager)
        assert settings.embedding_model == "text-embedding-3-large"
