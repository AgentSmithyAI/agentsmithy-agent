from __future__ import annotations

from .base import OSAdapter
from .posix import PosixAdapter
from .windows import WindowsAdapter


def get_os_adapter() -> OSAdapter:
    """Return an OS-specific adapter instance.

    - Windows: WindowsAdapter
    - Others (Linux/macOS/BSD): PosixAdapter
    """
    import os

    if os.name == "nt":
        return WindowsAdapter()
    return PosixAdapter()


# Global adapter instance for convenience
_adapter = get_os_adapter()


def normalize_path(path: str) -> str:
    """Normalize path to use forward slashes (for storage in git/DB).

    On Windows: converts backslashes to forward slashes
    On POSIX: returns path as-is

    This ensures consistent path storage regardless of OS.
    """
    return _adapter.normalize_path(path)
