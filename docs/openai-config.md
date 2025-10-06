### OpenAI provider and settings

This project now isolates the OpenAI chat provider in `agentsmithy_server/core/providers/openai/provider.py` and supports a nested configuration structure for OpenAI-specific options.

Recommended `.agentsmithy/config.json` structure:

```json
{
  "model": "gpt-5",               // global default (kept for back-compat)
  "temperature": 0.7,
  "max_tokens": 4000,
  "embedding_model": "text-embedding-3-small",

  "openai": {
    "api_key": "${OPENAI_API_KEY}",
    "base_url": null, // e.g. "http://localhost:1234/v1" for local servers

    "chat": {
      // Overrides for OpenAI chat only (if set, take precedence over globals)
      // "model": "gpt-5",
      // "temperature": 0.7,
      // "max_tokens": 4000,

      // Extended per-model options passed through to the SDK
      // For Responses family (gpt-5/gpt-5-mini) these are set as top-level kwargs
      // For Chat Completions family these go under model_kwargs
      "options": {
        // Example Responses options:
        // "reasoning": { "summary": "auto" }
      }
    },

    "embeddings": {
      // "model": "text-embedding-3-small",
      "options": {
        // Any extra kwargs forwarded to OpenAIEmbeddings
      }
    }
  }
}
```

Environment variables remain supported for legacy flat keys:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

### Class layout

- Chat provider: `agentsmithy_server.core.providers.openai.provider.OpenAIProvider`
- Embeddings provider: `agentsmithy_server.core.providers.openai.provider_embeddings.OpenAIEmbeddingsProvider`
- OpenAI model specs: `agentsmithy_server.core.providers.openai.models.*`
  - Base: `_base.OpenAIModelSpec`
  - Responses family base: `_responses_base._ResponsesFamilySpec`
  - Models: `gpt5`, `gpt5_mini` (registered via decorator)

### Backward compatibility

- Existing imports still work: `from agentsmithy_server.core import OpenAIProvider`.
- Flat settings (`model`, `temperature`, `max_tokens`, `embedding_model`, `openai_api_key`, `openai_base_url`) continue to work if nested keys are not provided.


