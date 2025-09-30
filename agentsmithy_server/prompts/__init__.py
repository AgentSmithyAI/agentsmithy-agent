"""Prompt templates and utilities.

Naming: files and symbols are named per agent for clarity.
"""

from .inspector import INSPECTOR_SYSTEM, build_inspector_human
from .universal import UNIVERSAL_SYSTEM

__all__ = [
    "UNIVERSAL_SYSTEM",
    "INSPECTOR_SYSTEM",
    "build_inspector_human",
]
