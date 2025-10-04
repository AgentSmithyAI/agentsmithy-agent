from __future__ import annotations

import os
from typing import Final

from .types import Vendor

# Central mapping of vendor -> API key environment variable name
API_KEY_ENV_BY_VENDOR: Final[dict[Vendor, str]] = {
    Vendor.OPENAI: "OPENAI_API_KEY",
    Vendor.ANTHROPIC: "ANTHROPIC_API_KEY",
    Vendor.XAI: "XAI_API_KEY",
    Vendor.DEEPSEEK: "DEEPSEEK_API_KEY",
    # OTHER (llama/local) also uses OPENAI_API_KEY because they use ChatOpenAI class
    Vendor.OTHER: "OPENAI_API_KEY",
}


def get_api_key_env_var(vendor: Vendor) -> str | None:
    """Return the API key env var name for a given vendor, if defined."""
    return API_KEY_ENV_BY_VENDOR.get(vendor)


def set_api_key_env(vendor: Vendor, api_key: str) -> None:
    """Set the appropriate API key environment variable for the vendor if known.

    Uses os.environ.setdefault to avoid overwriting already-configured variables.
    """
    env_var = get_api_key_env_var(vendor)
    if env_var and api_key:
        os.environ.setdefault(env_var, api_key)
