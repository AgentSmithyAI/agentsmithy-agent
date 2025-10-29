from __future__ import annotations

import os
import shutil
from typing import Any

from .base import BaseOSAdapter

# Locale defaults for Windows-friendly English output
WINDOWS_LOCALE_DEFAULTS = {
    # Many CLI tools respect these even on Windows when using MSYS/MinGW ports
    "LC_ALL": "C",
    "LC_MESSAGES": "C",
    "LANG": "C",
    # For native Windows apps, these have limited effect; kept for consistency
    "LANGUAGE": "en_US:en",
}


class WindowsAdapter(BaseOSAdapter):
    def english_locale_env(self, user_env: dict[str, str] | None) -> dict[str, str]:
        import os as _os

        base = _os.environ.copy()
        base.update(WINDOWS_LOCALE_DEFAULTS)
        if user_env:
            base.update({str(k): str(v) for k, v in user_env.items()})
        return base

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

    def normalize_path(self, path: str) -> str:
        """Normalize Windows path to use forward slashes.

        Replaces backslashes with forward slashes for consistent storage
        in git/database regardless of OS.
        """
        return path.replace("\\", "/")
