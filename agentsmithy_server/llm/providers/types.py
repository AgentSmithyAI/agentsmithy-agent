from __future__ import annotations

from enum import Enum


class Vendor(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    OTHER = "other"
