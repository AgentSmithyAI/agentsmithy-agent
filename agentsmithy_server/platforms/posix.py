from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import BaseOSAdapter

# Locale defaults for POSIX to force English
POSIX_LOCALE_DEFAULTS = {
    "LC_ALL": "C",
    "LC_MESSAGES": "C",
    "LANG": "C",
    "LANGUAGE": "en_US:en",
}

# NOTE: Keep previous behavior but extend coverage; do not remove prior entries.
# Two lists as requested: where to search and what executable names to try.
SHELL_SEARCH_DIRS: tuple[str, ...] = (
    # Core POSIX locations
    "/bin",
    "/usr/bin",
    "/usr/local/bin",
    "/sbin",
    "/usr/sbin",
    "/usr/local/sbin",
    "/opt/bin",
    # Linux distributions and Nix/Guix profiles
    "/run/current-system/sw/bin",  # NixOS
    "/run/current-system/profile/bin",  # Guix System
    # pkgsrc / BSD userland
    "/usr/pkg/bin",
    "/usr/pkg/sbin",
    # macOS third-party package managers
    "/opt/homebrew/bin",  # Homebrew (Apple Silicon)
    "/opt/homebrew/sbin",
    "/usr/local/opt/bin",  # Older Homebrew remnants
    "/opt/local/bin",  # MacPorts
    "/opt/local/sbin",
    # Solaris/illumos POSIX userland
    "/usr/xpg4/bin",
    # Android/Termux (various partitions and historical paths)
    "/system/bin",
    "/system/xbin",
    "/vendor/bin",
    "/product/bin",
    "/apex/com.android.runtime/bin",
    "/data/data/com.termux/files/usr/bin",
    "/data/data/com.termux/files/usr/sbin",
    # iOS jailbreak (rootful and rootless Procursus)
    "/var/jb/bin",
    "/var/jb/usr/bin",
    "/var/jb/usr/local/bin",
)

# Preference: standard POSIX shells first, then common alternatives; retain previous names and extend.
SHELL_EXECUTABLES: tuple[str, ...] = (
    # Strictly POSIX-favored first
    "sh",
    # Widely deployed POSIX-ish shells
    "bash",
    "dash",
    "ksh",
    "mksh",
    "oksh",
    "ash",
    # Others (lower priority)
    "zsh",
    "fish",
    "yash",
    # BSD C shells (kept to not regress behavior if relied upon)
    "tcsh",
    "csh",
)


def _is_executable(path: str | os.PathLike[str]) -> bool:
    try:
        p = Path(path)
        return p.is_file() and os.access(p, os.X_OK)
    except Exception:
        return False


class PosixAdapter(BaseOSAdapter):
    def english_locale_env(self, user_env: dict[str, str] | None) -> dict[str, str]:
        import os as _os

        base = _os.environ.copy()
        base.update(POSIX_LOCALE_DEFAULTS)
        if user_env:
            base.update({str(k): str(v) for k, v in user_env.items()})
        return base

    def detect_shell(self) -> str | None:
        # 1) Respect SHELL if it points to an existing executable
        shell = os.environ.get("SHELL")
        if shell and _is_executable(shell):
            return shell

        # 2) Use login shell from passwd database
        try:
            import pwd

            pw_shell = pwd.getpwuid(os.getuid()).pw_shell
            if pw_shell and _is_executable(pw_shell):
                return pw_shell
        except Exception:
            pass

        # 3) Try combinations of known dirs and shell names (POSIX-first priority)
        for name in SHELL_EXECUTABLES:
            for d in SHELL_SEARCH_DIRS:
                p = f"{d}/{name}"
                if _is_executable(p):
                    return p

        # 4) Fallback to PATH lookup for common shells (same preference order)
        try:
            import shutil

            for name in SHELL_EXECUTABLES:
                q = shutil.which(name)
                if q and _is_executable(q):
                    return q
        except Exception:
            pass

        # 5) Last resort
        return "/bin/sh"

    def make_shell_exec(self, command: str) -> tuple[list[str], dict[str, Any]]:
        # Always run through POSIX shell with -c; start a new session so we can kill the group on timeout
        shell_path = self.detect_shell() or "/bin/sh"
        argv = [shell_path, "-c", command]
        kwargs = {"start_new_session": True}
        return argv, kwargs

    def terminate_process(self, proc: Any) -> None:
        try:
            import os as _os
            import signal

            # Kill the whole process group if possible
            if getattr(proc, "pid", None):
                try:
                    _os.killpg(proc.pid, signal.SIGKILL)
                    return
                except Exception:
                    pass
            proc.kill()
        except Exception:
            pass
