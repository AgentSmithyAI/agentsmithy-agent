"""Ollama provider package.

Provides OpenAI-compatible adapter for Ollama local models.
"""

from .adapter import create_ollama_adapter
from .models import OllamaModelSpec

__all__ = ["create_ollama_adapter", "OllamaModelSpec"]
