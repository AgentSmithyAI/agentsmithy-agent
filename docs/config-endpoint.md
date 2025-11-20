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

**Layering overview**
- The runtime loads the global file, then overlays any project-level overrides (defaults → global → local).
- Only the global layer is writable via `/api/config`, so new providers and model bindings apply to every workspace that shares the same user config.
- A filesystem watcher re-validates the merged result after each change and updates `status.json`.
- A baseline `providers.openai` entry is always present (with `null` values) so the UI can render empty fields before anything is configured. Additional providers only appear after you create them.

## Hot Reload

**Configuration changes apply immediately without server restart.**

When updating via `PUT /api/config`:
1. Config is saved to file
2. Orchestrator is invalidated
3. Next request uses new config

## Endpoints

### GET /api/config

Returns the current provider catalog plus the model → provider map. Nothing else is surfaced, keeping the payload small and predictable.

`metadata` mirrors the config so the UI can render form controls without hard-coded enums:

- `provider_types`: allowed values for `providers.<name>.type`
- `providers`: every configured provider (name, type, whether an API key is set)
- `workloads`: each workload entry (name, provider, model) so the UI can render task-specific controls
- `agent_provider_slots`: every `models.*.(workload|provider)` path that must reference an existing workload/provider entry
- `model_catalog`: supported model IDs grouped by provider/vendor (chat vs embeddings); use it to populate model dropdowns or autocomplete hints

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
      },
    },
    "workloads": {
      "reasoning":    { "provider": "openai", "model": "gpt-5",             "options": {} },
      "execution":    { "provider": "openai", "model": "gpt-5-mini",        "options": {} },
      "summarization":{ "provider": "openai", "model": "gpt-5-mini",        "options": {} },
      "embeddings":   { "provider": "openai", "model": "text-embedding-3-small", "options": {} }
    },
    "models": {
      "agents": {
        "writer":   { "workload": "reasoning" }
      },
      "embeddings": { "workload": "embeddings" },
      "summarization": { "workload": "summarization" }
    }
  },
  "metadata": {
    "provider_types": ["openai", "anthropic", "xai", "deepseek", "other"],
    "providers": [
      { "name": "openai", "type": "openai", "has_api_key": true }
    ],
    "workloads": [
      { "name": "reasoning", "provider": "openai", "model": "gpt-5" },
      { "name": "execution", "provider": "openai", "model": "gpt-5-mini" },
      { "name": "summarization", "provider": "openai", "model": "gpt-5-mini" },
      { "name": "embeddings", "provider": "openai", "model": "text-embedding-3-small" }
    ],
    "agent_provider_slots": [
      { "path": "models.agents.writer.workload", "workload": "reasoning" },
      { "path": "models.embeddings.workload", "workload": "embeddings" },
      { "path": "models.summarization.workload", "workload": "summarization" }
    ],
    "model_catalog": {
      "openai": {
        "chat": ["gpt-5", "gpt-5-mini"],
        "embeddings": ["text-embedding-3-small", "text-embedding-3-large"]
      }
    }
  }
}
```

**Example:**

```bash
curl http://localhost:8765/api/config
```

### Rendering recommendations

Treat `/api/config` as the single source of truth. Every dropdown on the UI should be populated from `metadata`, and every text field should write back into `config`.

1. **Providers (credentials layer)**
   - Limited enum for types: `metadata.provider_types`. Bind this to the `type` select inside each provider row.
   - Provider rows themselves come from `config.providers`. Render editable inputs for `api_key`, `base_url`, `options` here.
   - Use `metadata.providers[*]` (name, type, `has_api_key`) to build provider pickers elsewhere and to surface “key missing” warnings.

2. **Workloads (task → model bindings)**
   - `config.workloads` is where the user actually picks a provider + model per task (`reasoning`, `execution`, `summarization`, `embeddings`, custom slots, etc.).
   - `metadata.workloads` mirrors this data with `{name, provider, model}` so the UI can easily render workload selectors without walking the config tree.
   - When the workload form needs a provider dropdown, use `metadata.providers`. When it needs a model dropdown, use `metadata.model_catalog[vendor][category]`:
     - vendor = the provider’s `type` (e.g. `openai`);
     - category = `"chat"` for agent workloads or `"embeddings"` for embedding workloads.
   - If a provider has no catalog entry (custom/other), fall back to free-form input but still write it under `config.workloads.<name>.model`.

3. **Slot wiring (`models.*`)**
   - `metadata.agent_provider_slots` enumerates every config path the UI should expose. The suffix tells you which selector to render:
     - Path ending in `.workload` → show a dropdown populated from `config.workloads` / `metadata.workloads`.
     - Path ending in `.provider` → show a provider dropdown sourced from `metadata.providers` (legacy compatibility).
   - When the user changes a slot binding, update the corresponding entry inside `config.models` and submit the diff via `PUT /api/config`.

4. **Model catalog**
   - `metadata.model_catalog` groups supported model IDs by vendor and category. Use it for autocomplete lists, tooltips, or validation (“Pick one of these known models for OpenAI chat”).
   - Because the catalog is delivered by the backend, new models appear automatically without a frontend release.

With this approach the UI never hardcodes provider types, workloads, or model names. All limits come from the metadata payload, and edits go straight into the `config` object submitted back to the server.

### PUT /api/config

Updates one or more configuration values. The changes are persisted to the configuration file and take effect immediately.

**Request Body:**

```json
{
  "config": {
    "workloads": {
      "reasoning": {
        "model": "gpt-4.1-preview"
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
  "config": {
    "workloads": {
      "reasoning": {
        "provider": "openai",
        "model": "gpt-4.1-preview",
        "options": {}
      }
    },
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
      "workloads": {
        "reasoning": {
          "model": "gpt-4.1-preview"
        }
      }
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

### Point a workload to OpenRouter (custom endpoint)

```bash
curl -X PUT http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "providers": {
        "openrouter": {
          "type": "openai",
          "api_key": "sk-openrouter-key",
          "base_url": "https://openrouter.ai/api/v1"
        }
      },
      "workloads": {
        "execution": {
          "provider": "openrouter",
          "model": "anthropic/claude-3-haiku"
        }
      }
    }
  }'
```

### View Current Config

```bash
curl http://localhost:8765/api/config | jq .
```

## Common configuration scenarios

| Scenario | How to configure |
| --- | --- |
| **Single OpenAI account, defaults suit me** | Set `providers.openai.api_key` (and optionally `base_url`). Leave `config.workloads.*` untouched — every task inherits this provider/model pairing. |
| **Different models for reasoning vs execution** | Update `config.workloads.reasoning.model` and `config.workloads.execution.model` via the endpoint. Both workloads can still point to `provider: "openai"` if they share the same key. |
| **Use OpenRouter or another OpenAI-compatible proxy** | Add a provider entry with its endpoint/key, e.g. `providers.openrouter`. Point the relevant workloads (`execution`, `summarization`, etc.) to that provider and choose a model from the catalog (e.g. `anthropic/claude-3-haiku`). |
| **Dedicated credentials for embeddings** | Create another provider (maybe `providers.embeddings`) with its own key. Set `config.workloads.embeddings.provider` to that entry so all embedding calls use the dedicated account/endpoint. |
| **Local OpenAI-compatible server (Ollama, LM Studio)** | Add a provider with `type: "openai"`, `api_key`: `"not-needed"` (or whatever the server expects), `base_url`: `"http://localhost:11434/v1"`. Point selected workloads to it. |
| **Future non-OpenAI vendors (Anthropic, xAI, DeepSeek)** | Add `providers.<name>` with `type` set to the vendor and capture credentials now. Even if the adapter isn’t implemented yet, the config stays forward-compatible; once the backend supports it, workloads referencing that provider will start working automatically. |

Remember: credentials live in `providers.*`, workloads pick the provider/model per task, and `models.*` wire workloads into actual features. Always use `metadata` from `/api/config` to populate dropdowns so the UI adapts when we add new provider types or tasks.


