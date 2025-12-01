# Provider Configuration

## Overview

AgentSmithy supports configuring multiple provider instances with different configurations. This allows you to use different OpenAI-compatible servers or different API keys for different agents.

## Configuration Methods

AgentSmithy supports two main configuration methods:

1. **Environment Variables** (`.env` file in workdir) — Quick setup for basic configuration
2. **Configuration File** (`.agentsmithy/config.json`) — Advanced multi-provider setup

### Environment Variables

Create a `.env` file in your workdir with the following variables:

```bash
# Required
OPENAI_API_KEY=sk-your-api-key-here

# Optional model configuration
MODEL=gpt-5.1-codex
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_BASE_URL=https://api.openai.com/v1

# Optional server configuration
SERVER_HOST=localhost
SERVER_PORT=8765
LOG_LEVEL=INFO
```

The `.env` file is automatically loaded on server startup. Environment variables provide a simple way to configure basic settings without editing JSON files.

### Configuration File

For advanced scenarios (multiple providers, different models per agent, etc.), use `.agentsmithy/config.json` in your workdir. See the sections below for detailed configuration options.

## Configuration Structure

### Provider Definitions

Each provider entry describes **credentials + transport** — API key, base URL, headers/options. Keep one entry per physical endpoint or account:

```json
{
  "providers": {
    "openai": {
      "type": "openai",
      "api_key": "sk-openai-key",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    },
    "openrouter": {
      "type": "openai",
      "api_key": "sk-openrouter-key",
      "base_url": "https://openrouter.ai/api/v1",
      "options": {}
    },
    "ollama": {
      "type": "ollama",
      "base_url": "http://localhost:11434/v1",
      "options": {}
    }
  }
}
```

### Workloads

Workloads connect a provider to a specific model. **Workload names are typically model names** for clarity:

```json
{
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
  }
}
```

**Note:** Default workloads are auto-generated from the model catalog. You only need to define custom workloads for:
- Using a different provider (e.g., OpenRouter, Ollama)
- Custom model options
- Models not in the default catalog

### Workload Fields

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | Reference to a provider name |
| `model` | string | Model name to use |
| `kind` | "chat" \| "embeddings" \| null | Workload type. Auto-detected if null |
| `options` | object | Model-specific options (temperature, etc.) |

### Model References

`models.*` reference workloads by name:

```json
{
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

## Provider Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Provider type: "openai", "ollama", "anthropic", "xai", "deepseek", "other" |
| `api_key` | string/null | API key for authentication |
| `base_url` | string/null | Base URL for the API endpoint |
| `options` | object | Additional provider-specific options |

## Examples

### Default Configuration (OpenAI)

Minimal config - just set the API key:

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

Default workloads are auto-generated for all supported models.

### Local Ollama Server

```json
{
  "providers": {
    "ollama": {
      "type": "ollama",
      "base_url": "http://localhost:11434/v1"
    }
  },
  "workloads": {
    "llama3:70b": {
      "provider": "ollama",
      "model": "llama3:70b"
    }
  },
  "models": {
    "agents": {
      "universal": { "workload": "llama3:70b" }
    }
  }
}
```

**Note:** Ollama models are dynamically discovered from the Ollama API when the server is running.

### OpenRouter (Multiple Models)

```json
{
  "providers": {
    "openrouter": {
      "type": "openai",
      "api_key": "sk-openrouter-key",
      "base_url": "https://openrouter.ai/api/v1"
    }
  },
  "workloads": {
    "claude-3-opus": {
      "provider": "openrouter",
      "model": "anthropic/claude-3-opus"
    },
    "gemini-pro": {
      "provider": "openrouter",
      "model": "google/gemini-pro"
    }
  },
  "models": {
    "agents": {
      "universal": { "workload": "claude-3-opus" }
    }
  }
}
```

### Multiple OpenAI Accounts

```json
{
  "providers": {
    "openai-prod": {
      "type": "openai",
      "api_key": "sk-prod-key"
    },
    "openai-dev": {
      "type": "openai",
      "api_key": "sk-dev-key"
    }
  },
  "workloads": {
    "prod-gpt5": {
      "provider": "openai-prod",
      "model": "gpt-5.1-codex"
    },
    "dev-gpt5-mini": {
      "provider": "openai-dev",
      "model": "gpt-5.1-codex-mini"
    }
  }
}
```

### Azure OpenAI

```json
{
  "providers": {
    "azure": {
      "type": "openai",
      "api_key": "your-azure-key",
      "base_url": "https://your-resource.openai.azure.com/",
      "options": {
        "api_version": "2024-02-01"
      }
    }
  }
}
```

## Auto-Generated Workloads

Default workloads are automatically generated from the model catalog:

- **OpenAI chat models**: `gpt-5.1`, `gpt-5.1-codex`, `gpt-5.1-codex-mini`
- **OpenAI embedding models**: `text-embedding-3-small`, `text-embedding-3-large`
- **Ollama models**: Dynamically discovered from running Ollama server

When you configure a custom workload with the same name, your settings override the defaults.

## Workload Kind Auto-Detection

The `kind` field determines whether a workload is for chat or embeddings:

- **Explicit**: Set `"kind": "chat"` or `"kind": "embeddings"`
- **Auto-detect**: Leave `kind` as `null` or omit it — detected from model name:
  - Models containing "embedding" → `embeddings`
  - Everything else → `chat`

Known embedding models (auto-detected):
- OpenAI: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
- Ollama: `nomic-embed-text`, `mxbai-embed-large`, `all-minilm`, `snowflake-arctic-embed`

## Model Types

### Agent Models

- **universal**: Main agent used for general-purpose tasks (strong model recommended)
- **inspector**: Project inspector agent (can use weaker model)

### Summarization Model

The `summarization` model generates dialog history summaries. Use a weaker/cheaper model to optimize costs:

```json
{
  "models": {
    "agents": {
      "universal": { "workload": "gpt-5.1-codex" }
    },
    "summarization": { "workload": "gpt-5.1-codex-mini" }
  }
}
```

### Embeddings Model

The `embeddings` model is used for RAG (Retrieval-Augmented Generation) operations.

## Benefits

1. **Multiple Endpoints**: Use different OpenAI-compatible servers for different agents
2. **Cost Optimization**: Route workloads to appropriate models (strong for reasoning, cheap for summarization)
3. **Development/Production Separation**: Use different configurations for different environments
4. **Local Development**: Use Ollama for development while keeping production configs separate
5. **Fallback Support**: Configure multiple providers for redundancy
6. **Any Model**: Use any model from any provider — no validation restrictions
