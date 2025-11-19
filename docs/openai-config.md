### OpenAI provider and settings

This project now isolates the OpenAI chat provider in `agentsmithy/core/providers/openai/provider.py` and supports a nested configuration structure for OpenAI-specific options.

Recommended `.agentsmithy/config.json` structure:

```jsonc
{
  "providers": {
    "openai": {
      "api_key": "${OPENAI_API_KEY}", // or set via env
      "base_url": "https://api.openai.com/v1",
      "options": {
        // Provider-wide options forwarded to OpenAI chat SDK
      },
      "embeddings": {
        "options": {
          // Embeddings-specific kwargs forwarded to OpenAIEmbeddings
        }
      }
    }
  },
  "workloads": {
    "reasoning":    { "provider": "openai", "model": "gpt-5" },
    "execution":    { "provider": "openai", "model": "gpt-5-mini" },
    "summarization":{ "provider": "openai", "model": "gpt-5-mini" },
    "embeddings":   { "provider": "openai", "model": "text-embedding-3-small" }
  },
  "models": {
    "agents": {
      "universal": { "workload": "reasoning" },
      "inspector": { "workload": "execution" }
    },
    "embeddings": { "workload": "embeddings" }
  }
}
```

Environment variables supported (can be set in `.env` file in workdir):

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL` (default model for agents)
- `EMBEDDING_MODEL` (model for embeddings)

The server automatically loads `.env` from the workdir on startup.

### Class layout

- Chat provider: `agentsmithy.core.providers.openai.provider.OpenAIProvider`
- Embeddings provider: `agentsmithy.core.providers.openai.provider_embeddings.OpenAIEmbeddingsProvider`
- OpenAI model specs: `agentsmithy.core.providers.openai.models.*`
  - Base: `_base.OpenAIModelSpec`
  - Responses family base: `_responses_base._ResponsesFamilySpec`
  - Models: `gpt5`, `gpt5_mini` (registered via decorator)

### Compatibility

- Existing imports still work: `from agentsmithy.core import OpenAIProvider`.


