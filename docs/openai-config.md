# OpenAI Provider Configuration

This document covers OpenAI-specific configuration and provider architecture.

## Quick Start

Minimal configuration in `.agentsmithy/config.json`:

```json
{
  "providers": {
    "openai": {
      "type": "openai",
      "api_key": "sk-your-key"
    }
  }
}
```

Or via environment variable:

```bash
export OPENAI_API_KEY=sk-your-key
```

Default workloads and models are auto-generated. No additional configuration needed.

## Full Configuration Example

```json
{
  "providers": {
    "openai": {
      "type": "openai",
      "api_key": "sk-your-key",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    }
  },
  "workloads": {
    "gpt-5.1-codex": {
      "provider": "openai",
      "model": "gpt-5.1-codex",
      "kind": "chat",
      "options": {}
    },
    "gpt-5.1-codex-mini": {
      "provider": "openai",
      "model": "gpt-5.1-codex-mini",
      "kind": "chat",
      "options": {}
    },
    "text-embedding-3-small": {
      "provider": "openai",
      "model": "text-embedding-3-small",
      "kind": "embeddings",
      "options": {}
    }
  },
  "models": {
    "agents": {
      "universal": { "workload": "gpt-5.1-codex" },
      "inspector": { "workload": "gpt-5.1-codex-mini" }
    },
    "embeddings": { "workload": "text-embedding-3-small" },
    "summarization": { "workload": "gpt-5.1-codex-mini" }
  }
}
```

## Environment Variables

Supported environment variables (can be set in `.env` file in workdir):

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_BASE_URL` | Custom base URL (default: `https://api.openai.com/v1`) |
| `MODEL` | Default model for agents |
| `EMBEDDING_MODEL` | Model for embeddings |

The server automatically loads `.env` from the workdir on startup.

## Supported Models

### Chat Models

- `gpt-5.1` — Base GPT-5.1 model
- `gpt-5.1-codex` — Optimized for code tasks (recommended for universal agent)
- `gpt-5.1-codex-mini` — Lighter version for inspector/summarization

### Embedding Models

- `text-embedding-3-small` — Cost-effective embeddings
- `text-embedding-3-large` — Higher quality embeddings

## Dynamic Model Discovery

When an API key is configured, the system fetches available models from OpenAI's `/v1/models` endpoint. This ensures you always see the latest available models.

If the API key is not set or the request fails, a static fallback list is used.

## Workload Kind

Each workload has a `kind` field:

- `"chat"` — For chat/completion models
- `"embeddings"` — For embedding models
- `null` — Auto-detected from model name

Auto-detection rules:
- Models starting with `text-embedding-` → `embeddings`
- Everything else → `chat`

## Class Layout

| Class | Location |
|-------|----------|
| Chat provider | `agentsmithy.llm.providers.openai.provider.OpenAIProvider` |
| Embeddings provider | `agentsmithy.llm.providers.openai.provider_embeddings.OpenAIEmbeddingsProvider` |
| Model specs | `agentsmithy.llm.providers.openai.models.*` |
| Model catalog | `agentsmithy.llm.providers.openai.catalog.OpenAIModelCatalogProvider` |

### Model Specs

Model specifications define per-model settings:

- Base: `agentsmithy.llm.providers.openai.models._base.OpenAIModelSpec`
- Responses family: `agentsmithy.llm.providers.openai.models._responses_base._ResponsesFamilySpec`
- Registered models: `gpt5_1`, `gpt5_1_codex`, `gpt5_1_codex_mini`

Models are registered via decorator:

```python
@register_model("gpt-5.1-codex")
class GPT51CodexConfig(_ResponsesFamilySpec):
    ...
```

## Custom Models

You can use any model name — there's no validation restriction:

```json
{
  "workloads": {
    "custom-model": {
      "provider": "openai",
      "model": "ft:gpt-4:my-org:custom:id"
    }
  }
}
```

For models not in the registry, `CustomChatCompletionsSpec` is used as fallback.

## OpenAI-Compatible Endpoints

The OpenAI provider works with any OpenAI-compatible API:

- **OpenRouter**: `base_url: "https://openrouter.ai/api/v1"`
- **Azure OpenAI**: `base_url: "https://your-resource.openai.azure.com/"`
- **LM Studio**: `base_url: "http://localhost:1234/v1"`
- **vLLM**: `base_url: "http://localhost:8000/v1"`

Example for OpenRouter:

```json
{
  "providers": {
    "openrouter": {
      "type": "openai",
      "api_key": "sk-or-key",
      "base_url": "https://openrouter.ai/api/v1"
    }
  },
  "workloads": {
    "claude-3-opus": {
      "provider": "openrouter",
      "model": "anthropic/claude-3-opus"
    }
  }
}
```
