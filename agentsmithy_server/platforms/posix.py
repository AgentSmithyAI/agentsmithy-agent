from __future__ import annotations

import os
import sys
from pathlib import Path

from .base import BaseOSAdapter


class PosixAdapter(BaseOSAdapter):
    def detect_shell(self) -> str | None:
        shell = os.environ.get("SHELL")
        if shell:
            return shell
        # macOS preference, then generic POSIX fallback
        if os.name == "posix":
            if sys.platform == "darwin":
                for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
                    if Path(candidate).exists():
                        return candidate
        return "/bin/sh"
