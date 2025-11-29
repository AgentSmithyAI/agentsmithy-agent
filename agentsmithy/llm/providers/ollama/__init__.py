"""Ollama provider package.

Provides OpenAI-compatible adapter for Ollama local models.
"""

from .adapter import factory
from .models import OllamaModelSpec

__all__ = ["factory", "OllamaModelSpec"]
