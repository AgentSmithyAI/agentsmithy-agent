from __future__ import annotations

import os
import shutil

from .base import BaseOSAdapter


class WindowsAdapter(BaseOSAdapter):
    def detect_shell(self) -> str | None:
        # Prefer COMSPEC, fallback to cmd.exe, and detect PowerShell if default
        comspec = os.environ.get("COMSPEC")
        if comspec:
            return comspec
        # If powershell is the default shell in env, reflect it; otherwise cmd.exe
        ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        return comspec or ps or "cmd.exe"

    def shlex_split(self, command: str) -> list[str]:
        import shlex

        return shlex.split(command, posix=False)
