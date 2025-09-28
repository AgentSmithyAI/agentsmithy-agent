from __future__ import annotations

from typing import Any


def detect_openai_family(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("gpt-4o") or m.startswith("o1") or m.startswith("gpt-5"):
        return "responses"
    return "chat_completions"


def supports_temperature(model: str) -> bool:
    m = (model or "").lower()
    # Disable temperature for responses-family models (o1/gpt-4o/gpt-5)
    if m.startswith("gpt-4o") or m.startswith("o1") or m.startswith("gpt-5"):
        return False
    return True


def build_openai_langchain_kwargs(
    model: str,
    temperature: float | None,
    max_tokens: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (base_kwargs, model_kwargs) for ChatOpenAI depending on model family.

    - For chat-completions family, attach stream_options.include_usage=True
    - For responses family, do not attach stream_options (unsupported)
    """
    base_kwargs: dict[str, Any] = {
        "model": model,
        "streaming": True,
    }
    if temperature is not None and supports_temperature(model):
        base_kwargs["temperature"] = temperature

    model_kwargs: dict[str, Any] = {}
    fam = detect_openai_family(model)
    if fam == "chat_completions":
        # Usage is available on final chunk when include_usage is enabled
        model_kwargs["stream_options"] = {"include_usage": True}

    if max_tokens is not None:
        # ChatOpenAI binds to OpenAI API; non-Responses models accept max_tokens directly
        base_kwargs["max_tokens"] = max_tokens

    return base_kwargs, model_kwargs
