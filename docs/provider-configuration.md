# Provider Configuration

Starting from this version, AgentSmithy supports flexible provider configuration that allows you to:

1. Configure multiple LLM providers (OpenAI, local models, etc.)
2. Assign different models to different agents (inspector, universal)
3. Automatically resolve provider settings based on model name

## Configuration Structure

The configuration file `.agentsmithy/config.json` now supports two new sections:

### 1. Providers Section

Define settings for each provider:

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "base_url": null,
      "temperature": 0.7,
      "max_tokens": 4000,
      "reasoning_effort": "low"
    },
    "local": {
      "base_url": "http://localhost:8080/v1",
      "api_key": null,
      "temperature": 0.7,
      "max_tokens": 4000
    }
  }
}
```

**Provider types:**
- `openai` - OpenAI cloud API and compatible services
- `llama` - Local/self-hosted models (llama.cpp, vLLM, Granite, etc.)
- `anthropic` - Claude models (planned)
- `xai` - xAI models (planned)
- `deepseek` - DeepSeek models (planned)

### 2. Models Section

Configure models for agents and embeddings:

```json
{
  "models": {
    "agent": {
      "inspector": "granite-4.0-h-micro",
      "universal": "gpt-5"
    },
    "embedding": "text-embedding-3-small"
  }
}
```

## How It Works

1. **Model Assignment**: You specify which model each agent should use
2. **Provider Detection**: The system automatically detects the provider based on the model name
3. **Settings Application**: Provider-specific settings are applied to the model

### Configuration Merging

When you start the server:
1. Your `config.json` is loaded
2. It's **deep-merged** with default values in memory (your values take precedence)
3. Missing keys are filled from defaults automatically

**Important:** Your `config.json` file is **never modified** on server start. It only changes when:
- The file doesn't exist (minimal initial file is created)
- You explicitly update settings via API

This means:
- ✅ Your config file stays clean and minimal
- ✅ You only need to specify values you want to change
- ✅ Missing options are automatically filled from defaults
- ✅ Your file is never overwritten on server restart

### Model to Provider Mapping

The system uses pattern matching to determine the provider:

- `gpt-*`, `o1-*` → OpenAI provider
- `granite-*`, `llama-*`, `mistral-*`, `qwen-*` → Llama provider
- `claude-*` → Anthropic provider (planned)

## Example Configurations

### Using OpenAI for Universal Agent and Llama for Inspector

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "temperature": 0.7,
      "max_tokens": 4000
    },
    "llama": {
      "base_url": "http://localhost:11434/v1",
      "api_key": null,
      "temperature": 0.5,
      "max_tokens": 2000
    }
  },
  "agents": {
    "inspector": {
      "model": "granite-3.1-8b-instruct"
    },
    "universal": {
      "model": "gpt-5"
    }
  }
}
```

### Using Only Llama Models

```json
{
  "providers": {
    "llama": {
      "base_url": "http://localhost:8080/v1",
      "api_key": null,
      "temperature": 0.7,
      "max_tokens": 4000
    }
  },
  "agents": {
    "inspector": {
      "model": "llama-3.1-8b-instruct"
    },
    "universal": {
      "model": "llama-3.1-70b-instruct"
    }
  }
}
```

### Using Same Model for All Agents

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "temperature": 0.7
    }
  },
  "agents": {
    "inspector": {
      "model": "gpt-5-mini"
    },
    "universal": {
      "model": "gpt-5-mini"
    }
  }
}
```

## Backwards Compatibility

The system maintains backwards compatibility with the old configuration format:

- `openai_api_key` → Used as fallback if `providers.openai.api_key` is not set
- `openai_base_url` → Used as fallback if `providers.openai.base_url` is not set
- `model` → Used as fallback if agent-specific model is not configured
- `temperature`, `max_tokens` → Used as fallback for provider settings

## Special Model Support

### Granite Models

Models with "granite" in the name receive special handling:
- Uses `GraniteChatOpenAI` wrapper
- Automatically parses tool calls from XML format
- Compatible with llama.cpp server

### Standard OpenAI-Compatible Models

Other llama-based models use standard `ChatOpenAI` from LangChain:
- Works with any OpenAI-compatible API
- Supports function calling if the model does
- Compatible with vLLM, llama.cpp, and other servers

## Environment Variables

You can still use environment variables as overrides:

- `OPENAI_API_KEY` - Overrides `openai_api_key` in config
- `OPENAI_BASE_URL` - Overrides `openai_base_url` in config
- `MODEL` - Overrides `model` in config

## API Usage

### Creating Providers Programmatically

```python
from agentsmithy_server.core import create_provider_for_agent, create_provider_for_model

# Create provider for specific agent (uses agent's configured model)
provider = create_provider_for_agent("inspector")

# Create provider for specific model (auto-detects provider)
provider = create_provider_for_model("granite-3.1-8b-instruct")
```

### Adding Custom Adapters

```python
from agentsmithy_server.core.providers.registry import register_adapter_factory
from agentsmithy_server.core.providers.base_adapter import IProviderChatAdapter
from agentsmithy_server.core.providers.types import Vendor

class MyCustomAdapter(IProviderChatAdapter):
    def vendor(self) -> Vendor:
        return Vendor.OTHER
    
    def supports_temperature(self) -> bool:
        return True
    
    def build_langchain(self, *, temperature, max_tokens, reasoning_effort):
        return "my_package.MyLLM", {"model": self.model, "temperature": temperature}

def my_factory(model: str):
    if "mycustom" in model.lower():
        return MyCustomAdapter(model)
    return None

# Register before creating providers
register_adapter_factory(my_factory)
```

## Migration Guide

### From Old Config Format

**Old:**
```json
{
  "openai_api_key": "sk-...",
  "model": "gpt-5",
  "temperature": 0.7
}
```

**New (Recommended):**
```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "temperature": 0.7
    }
  },
  "models": {
    "agent": {
      "inspector": "gpt-5-mini",
      "universal": "gpt-5"
    },
    "embedding": "text-embedding-3-small"
  }
}
```

**Note**: The old format still works, but the new format is recommended for better control and clarity.

## Troubleshooting

### "No provider adapter found for model 'xyz'"

This means the model name doesn't match any registered adapter patterns. Either:
1. Use a supported model name pattern
2. Register a custom adapter for your model
3. Use a generic OpenAI-compatible name (e.g., prefix with "local-")

### Provider Settings Not Applied

1. Check that the provider section name matches the detected provider
2. Verify model name matches adapter patterns
3. Check config file syntax (valid JSON)
4. Review logs for provider detection messages

### Model Not Using Expected Provider

The system uses first-match in adapter registry. Check:
1. Model name patterns in adapter factories
2. Adapter registration order
3. Logs showing which adapter was selected

