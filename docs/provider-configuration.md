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
MODEL=gpt-4o
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
    "openai-shared": {
      "type": "openai",
      "api_key": "sk-openai-key",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    },
    "openrouter": {
      "type": "openai",
      "api_key": "sk-openrouter-key",
      "base_url": "https://openrouter.ai/api/v1",
      "options": {
        "default_provider": "anthropic"
      }
    }
  }
}
```

### Workloads and Model References

`workloads` connect a provider profile to a concrete model (or per-task overrides). Then `models.*` simply reference the workload by name:

```json
{
  "workloads": {
    "reasoning":  { "provider": "openai-shared", "model": "gpt-5" },
    "execution":  { "provider": "openai-shared", "model": "gpt-5-mini" },
    "summarizer": { "provider": "openai-shared", "model": "gpt-5-mini" },
    "embeddings": { "provider": "openai-shared", "model": "text-embedding-3-small" }
  },
  "models": {
    "agents": {
      "universal": {
        "workload": "reasoning"
      },
      "inspector": {
        "workload": "execution"
      }
    },
    "embeddings": {
      "workload": "embeddings"
    },
    "summarization": {
      "workload": "summarizer"
    }
  }
}
```

The `summarization` model is used for generating dialog summaries when history becomes too long. Using a weaker/cheaper model for summarization helps reduce costs while maintaining quality for the main agent work.

## Provider Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Provider type (currently only "openai") |
| `model` | string | Model name to use |
| `api_key` | string/null | API key for authentication |
| `base_url` | string/null | Base URL for the API endpoint |
| `options` | object | Additional provider-specific options |

## Examples

### Local OpenAI-compatible Server (Ollama)

**Note:** Port 11434 is Ollama's default port, not AgentSmithy's server port (which is 8765).

```json
{
  "providers": {
    "local-llm": {
      "type": "openai",
      "model": "gpt-4.1",
      "api_key": "not-needed",
      "base_url": "http://localhost:11434/v1",  // Ollama server
      "options": {}
    }
  },
  "models": {
    "agents": {
      "universal": {
        "provider": "local-llm"
      }
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
      "api_key": "sk-prod-key",
      "base_url": "https://api.openai.com/v1"
    },
    "openai-dev": {
      "type": "openai",
      "api_key": "sk-dev-key",
      "base_url": "https://api.openai.com/v1"
    }
  },
  "workloads": {
    "reasoning": { "provider": "openai-prod", "model": "gpt-5" },
    "execution": { "provider": "openai-dev", "model": "gpt-4.1" }
  }
}
```

### Azure OpenAI

```json
{
  "providers": {
    "azure": {
      "type": "openai",
      "model": "gpt-5",
      "api_key": "your-azure-key",
      "base_url": "https://your-resource.openai.azure.com/",
      "options": {
        "api_version": "2024-02-01"
      }
    }
  }
}
```

## Backwards Compatibility

The legacy configuration format is still supported:

```json
{
  "models": {
    "agents": {
      "universal": {
        "model": "gpt-5"
      }
    }
  },
  "providers": {
    "openai": {
      "api_key": null,
      "base_url": null
    }
  }
}
```

When no provider is specified, the system falls back to the default "openai" provider credentials.

## Model Types

### Agent Models

- **universal**: Main agent used for general-purpose tasks (strong model)
- **inspector**: Project inspector agent (can use weaker model)

### Summarization Model

The `summarization` model is specifically used for generating dialog history summaries. When a conversation becomes too long, the system automatically creates summaries to maintain context while reducing token usage.

**Best Practice**: Use a weaker/cheaper model (like `gpt-5-mini`) for summarization to optimize costs, while keeping strong models (like `gpt-5`) for actual agent work.

Example configuration:

```json
{
  "workloads": {
    "reasoning": { "provider": "openai-shared", "model": "gpt-5" },
    "summarization": { "provider": "openai-shared", "model": "gpt-5-mini" }
  }
}
```

### Embeddings Model

The `embeddings` model is used for RAG (Retrieval-Augmented Generation) operations.

## Benefits

1. **Multiple Endpoints**: Use different OpenAI-compatible servers for different agents
2. **Cost Optimization**: Route different workloads to different API keys or accounts (e.g., weak models for summarization, strong models for main work)
3. **Development/Production Separation**: Use different configurations for different environments
4. **Local Development**: Use local models for development while keeping production configs separate
5. **Fallback Support**: Configure multiple providers for redundancy
6. **Smart Resource Allocation**: Use powerful models where they matter and cheaper models for background tasks

