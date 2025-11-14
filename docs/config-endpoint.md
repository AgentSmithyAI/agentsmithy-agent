# Configuration API Endpoint

Retrieve and update AgentSmithy configuration at runtime via HTTP.

## Hot Reload

**Configuration changes apply immediately without server restart.**

When updating via `PUT /api/config`:
1. Config is saved to file
2. Orchestrator is invalidated
3. Next request uses new config

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

## Examples

### Set OpenAI API Key

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "sk-your-key",
          "base_url": "https://api.openai.com/v1"
        }
      }
    }
  }'
```

### Set Named Provider (recommended for new configs)

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "gpt5": {
          "api_key": "sk-your-key",
          "base_url": "https://api.openai.com/v1"
        }
      }
    }
  }'
```

### View Current Config

```bash
curl http://localhost:8765/api/config | jq .
```


