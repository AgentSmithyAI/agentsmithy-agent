from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agentsmithy_server.core.dialog_usage_storage import DialogUsageStorage
from agentsmithy_server.core.summarization.strategy import TokenStrategy
from agentsmithy_server.utils.logger import agent_logger

# Fixed policies kept in code for simplicity
KEEP_LAST_MESSAGES = 24
SUMMARY_INPUT_CHAR_BUDGET = 16000
SUMMARY_OUTPUT_CHAR_BUDGET = 8000


def _estimate_chars(messages: Iterable[BaseMessage]) -> int:
    total = 0
    for m in messages:
        try:
            total += len(getattr(m, "content", "") or "")
        except Exception:
            pass
    return total


async def maybe_compact_dialog(
    llm_provider: Any,
    dialog_messages: list[BaseMessage],
    project: Any | None = None,
    dialog_id: str | None = None,
) -> list[BaseMessage] | None:
    try:
        strategy = TokenStrategy()
        # Prefer real prompt token usage from last request if available
        prompt_tokens: int | None = None
        try:
            if project and dialog_id:
                usage_store = DialogUsageStorage(project, dialog_id)
                usage = usage_store.load()
                if usage:
                    prompt_tokens = usage.prompt_tokens
        except Exception:
            prompt_tokens = None

        decision = strategy.should_summarize(prompt_tokens)
        if not decision.should_summarize:
            return None

        total_msgs = len(dialog_messages)
        keep_last = decision.keep_last
        # Compute boundary and align it backward to the previous user message
        boundary = max(0, total_msgs - keep_last)
        try:
            while boundary > 0 and not isinstance(
                dialog_messages[boundary], HumanMessage
            ):
                boundary -= 1
        except Exception:
            pass
        # If boundary is at start, skip summarization (nothing to summarize before first user)
        if boundary <= 0:
            return None
        older = dialog_messages[:boundary]

        budget = SUMMARY_INPUT_CHAR_BUDGET
        chunks: list[str] = []
        used = 0
        for m in older:
            c = (getattr(m, "content", "") or "").strip()
            if not c:
                continue
            extra = len(c) + 1
            if used + extra > budget:
                remain = budget - used
                if remain > 50:
                    chunks.append(c[:remain] + " …")
                break
            chunks.append(c)
            used += extra

        if not chunks:
            return None

        summarize_prompt = (
            "You are summarizing a long coding conversation into a compact, technical brief.\n"
            "Preserve key facts, decisions, and file references.\n"
            "- Focus on actionable information needed to continue work.\n"
            "- Include file paths, function names, and error messages when present.\n"
            "- Keep code snippets minimal; include only essential lines.\n"
            "- End with a short bullet list of pending tasks if any.\n\n"
            + "\n\n".join(chunks)
        )

        summary_text_raw = await llm_provider.agenerate(
            [SystemMessage(content=summarize_prompt)], stream=False
        )
        summary_text = str(summary_text_raw or "").strip()
        if not summary_text:
            return None

        max_out = SUMMARY_OUTPUT_CHAR_BUDGET
        if len(summary_text) > max_out:
            summary_text = summary_text[: max_out - 1] + "…"

        header = "Dialog Summary (earlier turns):\n" + summary_text
        agent_logger.info(
            "Generated dialog summary",
            total_messages=total_msgs,
            keep_last=keep_last,
            input_chars=used,
            summary_len=len(summary_text),
        )
        return [SystemMessage(content=header)]
    except Exception as e:
        agent_logger.error("Dialog compaction failed", exception=e)
        return None
