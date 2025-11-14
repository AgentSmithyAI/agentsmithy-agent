# Configuration API Endpoint

## Overview

The configuration API endpoint allows you to retrieve and update the AgentSmithy configuration at runtime through HTTP requests. This provides a convenient way to manage configuration without manually editing files.

**🔑 Most Important Use Case: Setting API Keys**

The primary purpose of this endpoint is to easily configure your API keys (OpenAI, Anthropic, etc.) without manually editing configuration files. See the [Setting API Keys](#setting-api-keys) section below for quick start examples.

## Endpoints

### GET /api/config

Retrieves the complete configuration including both default values and user-defined settings.

**Response:**

```json
{
  "config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 2000,
    "server_host": "localhost",
    "server_port": 8765,
    "streaming_enabled": true,
    "providers": {
      "openai": {
        "api_key": "sk-...",
        "base_url": "https://api.openai.com"
      }
    }
  }
}
```

**Example:**

```bash
curl http://localhost:8765/api/config
```

### PUT /api/config

Updates one or more configuration values. The changes are persisted to the configuration file and take effect immediately.

**Request Body:**

```json
{
  "config": {
    "model": "gpt-4-turbo",
    "temperature": 0.9
  }
}
```

**Response:**

```json
{
  "success": true,
  "message": "Successfully updated 2 configuration key(s)",
  "config": {
    "model": "gpt-4-turbo",
    "temperature": 0.9,
    "max_tokens": 2000,
    ...
  }
}
```

**Example:**

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "model": "gpt-4-turbo",
      "temperature": 0.9
    }
  }'
```

## Features

### Hot Reload

Configuration changes made through the API endpoint are automatically detected by the config watcher. The system will:

1. Update the in-memory configuration
2. Persist changes to the config file
3. Notify registered callbacks about the change
4. Invalidate cached components (like orchestrator) to pick up new settings

### Nested Configuration

The API supports nested configuration structures. You can update nested values by providing the complete nested structure:

```json
{
  "config": {
    "providers": {
      "openai": {
        "api_key": "new-key",
        "base_url": "https://custom-endpoint.com"
      }
    }
  }
}
```

### Persistence

All configuration changes are immediately saved to the `config.json` file in your AgentSmithy project directory. Only user-defined values are saved (not defaults), keeping the config file clean and minimal.

## Error Handling

The API returns appropriate HTTP status codes for errors:

- **422 Unprocessable Entity**: Invalid request body format
- **500 Internal Server Error**: Configuration manager not initialized or other internal errors

## Setting API Keys

This is the most common and important use case for the configuration endpoint.

### Quick Start: Set OpenAI API Key

**Using curl:**

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "sk-your-actual-api-key-here",
          "base_url": "https://api.openai.com/v1"
        }
      }
    }
  }'
```

### Setting Multiple Provider Keys

You can configure multiple AI providers at once:

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "sk-your-openai-key",
          "base_url": "https://api.openai.com/v1"
        },
        "anthropic": {
          "api_key": "sk-ant-your-anthropic-key",
          "base_url": "https://api.anthropic.com"
        }
      }
    }
  }'
```

### Using Custom OpenAI-Compatible Endpoints

If you're using a proxy or custom OpenAI-compatible endpoint:

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "your-proxy-key",
          "base_url": "https://your-proxy.com/v1"
        }
      }
    }
  }'
```

### Verifying Your API Key Configuration

```bash
# Get full config
curl http://localhost:8765/api/config

# Or just check providers (with jq)
curl http://localhost:8765/api/config | jq '.config.providers'
```

## Other Use Cases

### Updating Model Settings

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "model": "gpt-4-turbo-preview",
      "temperature": 0.8,
      "max_tokens": 4096
    }
  }'
```

### Changing Provider Configuration

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "sk-new-key-here",
          "base_url": "https://api.openai.com/v1"
        }
      }
    }
  }'
```

### Updating Server Settings

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "server_host": "0.0.0.0",
      "server_port": 9000
    }
  }'
```

**Note:** Server host and port changes require a server restart to take effect.

## Integration with Frontend

The config endpoint is designed to work seamlessly with UI-based configuration management:

```javascript
// Fetch current configuration
async function getConfig() {
  const response = await fetch('http://localhost:8765/api/config');
  const data = await response.json();
  return data.config;
}

// Update configuration
async function updateConfig(updates) {
  const response = await fetch('http://localhost:8765/api/config', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ config: updates }),
  });
  const data = await response.json();
  return data;
}

// Example: Update model
await updateConfig({
  model: 'gpt-4-turbo',
  temperature: 0.9,
});
```

## Security Considerations

- The configuration API is exposed without authentication in the current implementation
- Consider restricting access to localhost or implementing authentication for production use
- Sensitive values like API keys are stored in plain text in the config file
- Use environment variables or secure secret management for production deployments

## Related Documentation

- [Configuration Management](./openai-config.md)
- [Provider Configuration](./provider-configuration.md)
- [Project Structure](./project-structure.md)

