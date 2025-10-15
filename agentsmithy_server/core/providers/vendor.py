from __future__ import annotations

from typing import Final

from .types import Vendor

# Central mapping of vendor -> API key environment variable name
API_KEY_ENV_BY_VENDOR: Final[dict[Vendor, str]] = {
    Vendor.OPENAI: "OPENAI_API_KEY",
    Vendor.ANTHROPIC: "ANTHROPIC_API_KEY",
    Vendor.XAI: "XAI_API_KEY",
    Vendor.DEEPSEEK: "DEEPSEEK_API_KEY",
    # Llama is local, no API key needed
    # For unknown/other vendors we intentionally do not set any variable.
}


def get_api_key_env_var(vendor: Vendor) -> str | None:
    """Return the API key env var name for a given vendor, if defined."""
    return API_KEY_ENV_BY_VENDOR.get(vendor)
