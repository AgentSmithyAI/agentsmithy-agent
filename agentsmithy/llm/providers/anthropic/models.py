"""Anthropic model specifications.

Anthropic uses the Messages API with specific features:
- Supports temperature (0.0-1.0)
- Supports max_tokens (required for Claude)
- Supports streaming with usage info
- Extended thinking available for Claude 4+ models via thinking parameter
"""

from __future__ import annotations

from typing import Any

from agentsmithy.llm.providers.model_spec import IModelSpec
from agentsmithy.llm.providers.types import Vendor

# Workload name -> full model ID (from /v1/models API)
# Short workload names for user convenience
ANTHROPIC_WORKLOADS: dict[str, str] = {
    "opus-4.5": "claude-opus-4-5-20251101",
    "sonnet-4.5": "claude-sonnet-4-5-20250929",
    "haiku-4.5": "claude-haiku-4-5-20251001",
    "opus-4.1": "claude-opus-4-1-20250805",
    "opus-4": "claude-opus-4-20250514",
    "sonnet-4": "claude-sonnet-4-20250514",
    "haiku-3.5": "claude-3-5-haiku-20241022",
    "haiku-3": "claude-3-haiku-20240307",
}

# All supported model IDs (derived from workloads)
SUPPORTED_ANTHROPIC_CHAT_MODELS = set(ANTHROPIC_WORKLOADS.values())

# Models that support extended thinking (Claude 4+)
EXTENDED_THINKING_MODELS = {
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
}


class AnthropicModelSpec(IModelSpec):
    """Model spec for Anthropic Claude models.

    Uses ChatAnthropic from langchain_anthropic.
    """

    def __init__(self, name: str):
        super().__init__(name=name, vendor=Vendor.ANTHROPIC)

    def supports_temperature(self) -> bool:
        # Extended thinking models don't support temperature
        return self.name not in EXTENDED_THINKING_MODELS

    def supports_extended_thinking(self) -> bool:
        """Check if model supports extended thinking."""
        return self.name in EXTENDED_THINKING_MODELS

    def build_langchain_kwargs(
        self, temperature: float | None, max_tokens: int | None, reasoning_effort: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build kwargs for ChatAnthropic.

        Anthropic requires max_tokens to be set.
        """
        base_kwargs: dict[str, Any] = {
            "model": self.name,
        }

        # max_tokens is required for Anthropic
        if max_tokens is not None:
            base_kwargs["max_tokens"] = max_tokens
        else:
            # Default max_tokens for Claude
            base_kwargs["max_tokens"] = 4096

        # Temperature (not supported for extended thinking models)
        if temperature is not None and self.supports_temperature():
            base_kwargs["temperature"] = temperature

        # Extended thinking configuration
        model_kwargs: dict[str, Any] = {}
        if self.supports_extended_thinking():
            # Extended thinking models require thinking budget
            # Map reasoning_effort to budget_tokens
            budget_map = {
                "low": 1024,
                "medium": 4096,
                "high": 16384,
            }
            budget_tokens = budget_map.get(reasoning_effort, 4096)
            model_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            }

        return base_kwargs, model_kwargs
