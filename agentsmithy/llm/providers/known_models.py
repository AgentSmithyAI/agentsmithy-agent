"""Known model classifications by provider.

Used to auto-detect workload kind (chat vs embeddings) when not explicitly set.
"""

from __future__ import annotations

from .types import Vendor

# Known embedding models by provider
# If a model is in this set, it's classified as "embeddings"
# Otherwise, it defaults to "chat"
KNOWN_EMBEDDING_MODELS: dict[Vendor, set[str]] = {
    Vendor.OPENAI: {
        "text-embedding-3-small",
        "text-embedding-3-large",
        "text-embedding-ada-002",
    },
    Vendor.OLLAMA: {
        "nomic-embed-text",
        "nomic-embed-text:latest",
        "mxbai-embed-large",
        "mxbai-embed-large:latest",
        "all-minilm",
        "all-minilm:latest",
        "snowflake-arctic-embed",
        "snowflake-arctic-embed:latest",
    },
    Vendor.ANTHROPIC: set(),  # Anthropic doesn't have public embedding models yet
    Vendor.XAI: set(),
    Vendor.DEEPSEEK: set(),
    Vendor.OTHER: set(),
}


def is_embedding_model(model: str, vendor: Vendor | str | None = None) -> bool:
    """Check if a model is a known embedding model.

    Args:
        model: Model name to check.
        vendor: Optional vendor to narrow the search.

    Returns:
        True if model is a known embedding model.
    """
    if vendor is not None:
        if isinstance(vendor, str):
            try:
                vendor = Vendor(vendor)
            except ValueError:
                vendor = None

        if vendor is not None:
            return model in KNOWN_EMBEDDING_MODELS.get(vendor, set())

    # Check all vendors
    for models in KNOWN_EMBEDDING_MODELS.values():
        if model in models:
            return True
    return False


def infer_workload_kind(model: str | None, vendor: Vendor | str | None = None) -> str:
    """Infer workload kind from model name.

    Args:
        model: Model name.
        vendor: Optional vendor hint.

    Returns:
        "embeddings" if model is known embedding model, "chat" otherwise.
    """
    if not model:
        return "chat"

    if is_embedding_model(model, vendor):
        return "embeddings"

    return "chat"
