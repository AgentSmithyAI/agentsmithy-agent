# Provider Configuration

## Overview

AgentSmithy supports configuring multiple provider instances with different configurations. This allows you to use different OpenAI-compatible servers or different API keys for different agents.

## Configuration Structure

### Provider Definitions

Each provider is defined in the `providers` section with a complete configuration:

```json
{
  "providers": {
    "gpt5": {
      "type": "openai",
      "model": "gpt-5",
      "api_key": "sk-your-openai-key-here",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    },
    "embeddings": {
      "type": "openai",
      "model": "text-embedding-3-small",
      "api_key": null,
      "base_url": null,
      "options": {}
    }
  }
}
```

### Model References

In the `models` section, reference providers by name:

```json
{
  "models": {
    "agents": {
      "universal": {
        "provider": "gpt5"
      },
      "inspector": {
        "provider": "gpt5"
      }
    },
    "embeddings": {
      "provider": "embeddings"
    },
    "summarization": {
      "provider": "gpt5-mini"
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
      "model": "gpt-5",
      "api_key": "sk-prod-key",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    },
    "openai-dev": {
      "type": "openai",
      "model": "gpt-4.1",
      "api_key": "sk-dev-key",
      "base_url": "https://api.openai.com/v1",
      "options": {}
    }
  },
  "models": {
    "agents": {
      "universal": {
        "provider": "openai-prod"
      },
      "inspector": {
        "provider": "openai-dev"
      }
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
  "providers": {
    "gpt5": {
      "type": "openai",
      "model": "gpt-5",
      "api_key": "sk-your-key",
      "base_url": "https://api.openai.com/v1"
    },
    "gpt5-mini": {
      "type": "openai",
      "model": "gpt-5-mini",
      "api_key": "sk-your-key",
      "base_url": "https://api.openai.com/v1"
    }
  },
  "models": {
    "agents": {
      "universal": {"provider": "gpt5"}
    },
    "summarization": {"provider": "gpt5-mini"}
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

