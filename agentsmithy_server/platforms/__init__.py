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
