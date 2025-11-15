# Configuration API Endpoint

Retrieve and update AgentSmithy configuration at runtime via HTTP.

## Config File Location

Configuration is stored in a user-level directory so it can be shared across all projects:

- **Linux**: `~/.config/agentsmithy/config.json` (respects `XDG_CONFIG_HOME`)
- **macOS**: `~/Library/Application Support/AgentSmithy/config.json`
- **Windows**: `%APPDATA%\AgentSmithy\config.json`

Override the location with the `AGENTSMITHY_CONFIG_DIR` environment variable if needed.
Legacy per-project configs under `<workdir>/.agentsmithy/config.json` are migrated automatically on first run.

## Server Startup Without API Key

**Server can start without API keys configured.**

- Server starts successfully even if no API key is set
- Shows warning in logs but doesn't crash
- `/api/config` endpoint is available immediately
- Set API key via endpoint, changes apply instantly via hot reload
- LLM requests will fail until API key is configured

**Check configuration status:**

Via HTTP:
```bash
curl http://localhost:8765/health
```

Or directly from `status.json` file:
```bash
cat .agentsmithy/status.json
```

Response includes configuration validation:

```json
{
  "server_status": "ready",
  "port": 8765,
  "config_valid": false,
  "config_errors": ["API key not configured"],
  ...
}
```

When `config_valid` is `false`, client should prompt user to configure API keys via `/api/config`.

**Config validation is updated automatically:**
- On server startup → checks config, writes to status.json
- On config change via `/api/config` → rechecks, updates status.json

## Configuration Storage

- **Global config (updated via `/api/config`):**
  - Linux: `${XDG_CONFIG_HOME:-~/.config}/agentsmithy/config.json`
  - macOS: `~/Library/Application Support/AgentSmithy/config.json`
  - Windows: `%APPDATA%\AgentSmithy\config.json`
  - Override path via `AGENTSMITHY_CONFIG_DIR`

- **Per-project overrides:** `.agentsmithy/config.json` in the project directory.
  - Optional file; merged on top of global config
  - Useful for project-specific API keys/models
  - Loosely treated as read-only (edit manually or via version control)

**Precedence:** defaults → global config → local project config.
The `/api/config` endpoint always writes to the global config file so changes apply to all projects.

**Как это устроено внутри:**
- Конфиг читается «слоями» через список `ConfigProvider` (глобальный файл, затем проектные оверрайды, позже можно добавить удалённые источники)
- Все слои горячо мерджатся, а записываем мы только в первый слой (глобальный)
- При изменении любого слоя watcher пересчитывает итоговый конфиг и триггерит инвалидацию на сервере
- В `providers` всегда присутствуют базовые секции `openai` и `anthropic` с `null`‑значениями, чтобы клиент мог отрисовать «общие» поля (API key, base URL и т.д.) даже до первого сохранения

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


