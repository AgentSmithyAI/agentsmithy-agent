"""Prompt templates and utilities for the agent.

Centralizes the system prompt, enforcement message, and shared constants.
"""

from .constants import MODIFICATION_KEYWORDS
from .system_prompt import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "MODIFICATION_KEYWORDS",
]
