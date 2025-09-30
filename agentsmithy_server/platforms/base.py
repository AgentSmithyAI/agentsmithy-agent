from __future__ import annotations

import platform
import sys
from typing import Any, Protocol


class OSAdapter(Protocol):
    def detect_shell(self) -> str | None: ...
    def os_context(self) -> dict[str, Any]: ...
    def shlex_split(self, command: str) -> list[str]: ...
    def make_shell_exec(self, command: str) -> tuple[list[str], dict[str, Any]]: ...
    def terminate_process(self, proc: Any) -> None: ...


class BaseOSAdapter:
    def detect_shell(self) -> str | None:
        raise NotImplementedError

    def os_context(self) -> dict[str, Any]:
        try:
            ctx: dict[str, Any] = {
                "platform": sys.platform,
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "shell": self.detect_shell(),
            }
            try:
                ctx["processor"] = platform.processor()
            except Exception:
                pass
            return ctx
        except Exception:
            return {}

    def shlex_split(self, command: str) -> list[str]:
        import shlex

        return shlex.split(command, posix=True)

    def make_shell_exec(self, command: str) -> tuple[list[str], dict[str, Any]]:
        """Build argv and extra subprocess kwargs to execute a command via system shell.

        Subclasses should override for platform-specific behavior.
        """
        raise NotImplementedError

    def terminate_process(self, proc: Any) -> None:
        """Terminate a running process tree appropriately for the platform.

        Subclasses should override; the default best-effort kill is provided for safety.
        """
        try:
            proc.kill()
        except Exception:
            pass
