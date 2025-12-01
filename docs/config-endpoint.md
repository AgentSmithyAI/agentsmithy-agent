# Configuration API Endpoint

Retrieve, update, and rename AgentSmithy configuration at runtime via HTTP.

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

## Configuration Scope

- **Global config (read/write):**
  - Linux: `${XDG_CONFIG_HOME:-~/.config}/agentsmithy/config.json`
  - macOS: `~/Library/Application Support/AgentSmithy/config.json`
  - Windows: `%APPDATA%\AgentSmithy\config.json`
  - Override via `AGENTSMITHY_CONFIG_DIR`

- **Per-project overrides (read-only):** `<workdir>/.agentsmithy/config.json`
  - Merged on top of the global file so a single repo can use different providers
  - Useful for project-specific API keys/models
  - Never modified via `/api/config`

## Hot Reload

**Configuration changes apply immediately without server restart.**

When updating via `PUT /api/config`:
1. Config is saved to file
2. Orchestrator is invalidated
3. Next request uses new config

## Endpoints

### GET /api/config

Returns the current configuration with metadata for UI rendering.

**Response:**

```json
{
  "config": {
    "providers": {
      "openai": {
        "type": "openai",
        "api_key": "sk-live-123",
        "base_url": "https://api.openai.com/v1",
        "options": {}
      }
    },
    "workloads": {
      "gpt-5.1-codex": {
        "provider": "openai",
        "model": "gpt-5.1-codex",
        "kind": null,
        "options": {}
      },
      "text-embedding-3-small": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "kind": null,
        "options": {}
      }
    },
    "models": {
      "agents": {
        "universal": { "workload": "gpt-5.1-codex" },
        "inspector": { "workload": "gpt-5.1-codex-mini" }
      },
      "embeddings": { "workload": "text-embedding-3-small" },
      "summarization": { "workload": "gpt-5.1-codex-mini" }
    }
  },
  "metadata": {
    "provider_types": ["openai", "ollama", "anthropic", "xai", "deepseek", "other"],
    "providers": [
      { "name": "openai", "type": "openai", "has_api_key": true }
    ],
    "workloads": [
      { "name": "gpt-5.1-codex", "provider": "openai", "model": "gpt-5.1-codex", "kind": "chat" },
      { "name": "gpt-5.1-codex-mini", "provider": "openai", "model": "gpt-5.1-codex-mini", "kind": "chat" },
      { "name": "text-embedding-3-small", "provider": "openai", "model": "text-embedding-3-small", "kind": "embeddings" }
    ],
    "agent_provider_slots": [
      { "path": "models.agents.universal.workload", "workload": "gpt-5.1-codex" },
      { "path": "models.agents.inspector.workload", "workload": "gpt-5.1-codex-mini" },
      { "path": "models.embeddings.workload", "workload": "text-embedding-3-small" },
      { "path": "models.summarization.workload", "workload": "gpt-5.1-codex-mini" }
    ],
    "model_catalog": {
      "openai": {
        "chat": ["gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-mini"],
        "embeddings": ["text-embedding-3-small", "text-embedding-3-large"]
      },
      "ollama": {
        "chat": ["llama3:70b", "mistral:7b"],
        "embeddings": []
      }
    }
  }
}
```

**Metadata fields:**

| Field | Description |
|-------|-------------|
| `provider_types` | Allowed values for `providers.<name>.type` |
| `providers` | Configured providers with status |
| `workloads` | All workloads with name, provider, model, and **kind** |
| `agent_provider_slots` | Config paths that reference workloads |
| `model_catalog` | Supported models by vendor, grouped by chat/embeddings |

**Important:** Workloads in metadata include `kind` field ("chat" or "embeddings") which is auto-detected from the model name if not explicitly set.

### PUT /api/config

Updates configuration values. Changes are persisted and take effect immediately.

**Request:**

```json
{
  "config": {
    "workloads": {
      "gpt-5.1-codex": {
        "provider": "openrouter",
        "model": "anthropic/claude-3-opus"
      }
    }
  }
}
```

**Response:**

```json
{
  "success": true,
  "message": "Successfully updated 1 configuration key(s)",
  "config": { ... },
  "metadata": { ... }
}
```

### POST /api/config/rename

Renames a workload or provider and updates all references.

**Request:**

```json
{
  "type": "workload",
  "old_name": "gpt-5.1-codex",
  "new_name": "my-reasoning-model"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Successfully renamed workload 'gpt-5.1-codex' to 'my-reasoning-model'",
  "old_name": "gpt-5.1-codex",
  "new_name": "my-reasoning-model",
  "updated_references": [
    "models.agents.universal.workload",
    "models.summarization.workload"
  ],
  "config": { ... },
  "metadata": { ... }
}
```

**Parameters:**

| Field | Type | Description |
|-------|------|-------------|
| `type` | "workload" \| "provider" | Entity type to rename |
| `old_name` | string | Current name |
| `new_name` | string | New name |

**Errors:**
- 400 if entity not found
- 400 if new name already exists
- 400 if old_name equals new_name

## Rendering Recommendations

Treat `/api/config` as the single source of truth.

### 1. Providers (credentials layer)

- `metadata.provider_types` → dropdown for provider type
- `config.providers` → editable fields for api_key, base_url, options
- `metadata.providers` → build provider pickers, show "key missing" warnings

### 2. Workloads (model bindings)

- `metadata.workloads` → list of available workloads with kind
- Filter by `kind` for appropriate dropdowns:
  - `kind: "chat"` for agent model selection
  - `kind: "embeddings"` for embedding model selection
- `model_catalog[vendor][category]` → model suggestions when creating workloads

### 3. Slot Wiring (models.*)

- `metadata.agent_provider_slots` → config paths to expose
- Paths ending in `.workload` → workload dropdown

### 4. Model Catalog

- `metadata.model_catalog` → autocomplete/suggestions for model names
- Grouped by vendor and category (chat/embeddings)
- **OpenAI models**: Fetched dynamically from API if api_key is set, otherwise static list
- **Ollama models**: Fetched dynamically from running Ollama server

## Examples

### Set OpenAI API Key

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openai": {
          "api_key": "sk-your-key"
        }
      }
    }
  }'
```

### Add Ollama Provider

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "ollama": {
          "type": "ollama",
          "base_url": "http://localhost:11434/v1"
        }
      },
      "workloads": {
        "llama3": {
          "provider": "ollama",
          "model": "llama3:70b"
        }
      }
    }
  }'
```

### Change Universal Agent Model

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "models": {
        "agents": {
          "universal": { "workload": "gpt-5.1-codex-mini" }
        }
      }
    }
  }'
```

### Rename Workload

```bash
curl -X POST http://localhost:8765/api/config/rename \
  -H "Content-Type: application/json" \
  -d '{
    "type": "workload",
    "old_name": "gpt-5.1-codex",
    "new_name": "main-reasoning"
  }'
```

### Delete Provider

Set value to `null` to delete:

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "old-provider": null
      }
    }
  }'
```

**Note:** Deletion fails if provider/workload is still referenced.

## Common Scenarios

| Scenario | How to configure |
|----------|------------------|
| **Single OpenAI account** | Set `providers.openai.api_key`. Default workloads are auto-generated. |
| **Different models per task** | Change `models.agents.universal.workload` and `models.agents.inspector.workload` to different workloads. |
| **Use OpenRouter** | Add provider with OpenRouter endpoint/key. Create workloads pointing to it with OpenRouter model names (e.g., `anthropic/claude-3-opus`). |
| **Local Ollama** | Add `providers.ollama` with `type: "ollama"`. Ollama models appear automatically in `model_catalog`. |
| **Custom model not in catalog** | Create a workload with any model name — no validation restrictions. |
