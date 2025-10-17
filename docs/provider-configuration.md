# Provider Configuration

## Overview

AgentSmithy supports configuring multiple provider instances with different configurations. This allows you to use different OpenAI-compatible servers or different API keys for different agents.

## Configuration Structure

### Provider Definitions

Each provider is defined in the `providers` section with a complete configuration:

```json
{
  "providers": {
    "gpt-local": {
      "type": "openai",
      "model": "gpt-oss:20b",
      "api_key": "dummy-key-for-local-server",
      "base_url": "http://localhost:11434/v1",  // Ollama default port
      "options": {}
    },
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
        "provider": "gpt-local"
      },
      "inspector": {
        "provider": "gpt5"
      }
    },
    "embeddings": {
      "provider": "embeddings"
    }
  }
}
```

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
      "model": "gpt-oss:20b",
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

## Benefits

1. **Multiple Endpoints**: Use different OpenAI-compatible servers for different agents
2. **Cost Optimization**: Route different workloads to different API keys or accounts
3. **Development/Production Separation**: Use different configurations for different environments
4. **Local Development**: Use local models for development while keeping production configs separate
5. **Fallback Support**: Configure multiple providers for redundancy

