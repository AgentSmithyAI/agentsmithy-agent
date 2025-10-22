from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentsmithy.config import settings

# No tokenizer imports; strategy relies on recorded prompt token usage

# Hardcoded policy values kept in code for simplicity
KEEP_LAST_MESSAGES = 24


@runtime_checkable
class SummarizationDecisionStrategy(Protocol):
    def should_summarize(self, prompt_tokens: int | None) -> SummarizationDecision: ...


class SummarizationDecision:
    def __init__(self, should_summarize: bool, keep_last: int = 0):
        self.should_summarize = should_summarize
        self.keep_last = keep_last


class TokenStrategy:
    """Trigger summarization when last recorded prompt token usage exceeds threshold."""

    def should_summarize(self, prompt_tokens: int | None) -> SummarizationDecision:
        if prompt_tokens is None:
            return SummarizationDecision(False)
        if prompt_tokens < settings.summary_trigger_token_budget:
            return SummarizationDecision(False)
        return SummarizationDecision(True, keep_last=KEEP_LAST_MESSAGES)
