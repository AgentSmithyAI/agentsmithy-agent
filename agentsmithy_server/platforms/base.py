from __future__ import annotations

import platform
import sys
from typing import Any, Protocol


class OSAdapter(Protocol):
    def detect_shell(self) -> str | None: ...
    def os_context(self) -> dict[str, Any]: ...
    def shlex_split(self, command: str) -> list[str]: ...


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
