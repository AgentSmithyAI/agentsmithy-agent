### OpenAI provider and settings

This project now isolates the OpenAI chat provider in `agentsmithy_server/core/providers/openai/provider.py` and supports a nested configuration structure for OpenAI-specific options.

Recommended `.agentsmithy/config.json` structure:

```jsonc
{
  "providers": {
    "openai": {
      "api_key": "${OPENAI_API_KEY}", // or set via env
      "base_url": null, // e.g. "http://localhost:1234/v1" for local servers
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
  "models": {
    "agents": {
      "universal": { "model": "gpt-5" },
      "inspector": { "model": "gpt-5-mini" }
    },
    "embeddings": { "model": "text-embedding-3-small" }
  }
}
```

Environment variables supported:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

### Class layout

- Chat provider: `agentsmithy_server.core.providers.openai.provider.OpenAIProvider`
- Embeddings provider: `agentsmithy_server.core.providers.openai.provider_embeddings.OpenAIEmbeddingsProvider`
- OpenAI model specs: `agentsmithy_server.core.providers.openai.models.*`
  - Base: `_base.OpenAIModelSpec`
  - Responses family base: `_responses_base._ResponsesFamilySpec`
  - Models: `gpt5`, `gpt5_mini` (registered via decorator)

### Compatibility

- Existing imports still work: `from agentsmithy_server.core import OpenAIProvider`.


