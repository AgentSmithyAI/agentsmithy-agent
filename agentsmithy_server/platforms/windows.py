from __future__ import annotations

import os
import shutil
from typing import Any

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

    def make_shell_exec(self, command: str) -> tuple[list[str], dict[str, Any]]:
        shell_path = self.detect_shell() or os.environ.get("COMSPEC", "cmd.exe")
        low = shell_path.lower()
        if low.endswith("powershell.exe") or low.endswith("pwsh.exe"):
            argv = [
                shell_path,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ]
            return argv, {}
        else:
            argv = [shell_path, "/d", "/s", "/c", command]
            return argv, {}

    def terminate_process(self, proc: Any) -> None:
        try:
            proc.kill()
        except Exception:
            pass
