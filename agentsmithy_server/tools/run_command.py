from __future__ import annotations

import asyncio
import os
import platform
import shlex
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base_tool import BaseTool


def _detect_shell() -> str | None:
    # Prefer explicit environment variables
    if os.name == "nt":
        return os.environ.get("COMSPEC") or "cmd.exe"
    return os.environ.get("SHELL") or "/bin/sh"


def _os_context() -> dict[str, Any]:
    try:
        ctx: dict[str, Any] = {
            "platform": sys.platform,
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "shell": _detect_shell(),
        }
        # Additional hints
        try:
            ctx["processor"] = platform.processor()
        except Exception:
            pass
        return ctx
    except Exception:
        return {}


class RunCommandArgs(BaseModel):
    command: str = Field(
        ..., description="Command to execute (interpreted by the system shell)"
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory to run the command in (optional)",
    )
    timeout: float = Field(
        default=60.0, description="Timeout in seconds before the command is killed"
    )
    env: dict[str, str] | None = Field(
        default=None, description="Additional environment variables to set"
    )
    max_output_bytes: int = Field(
        default=400_000,
        description=(
            "Maximum number of bytes to keep from stdout/stderr each; output will be truncated if exceeded"
        ),
    )
    encoding: str = Field(
        default="utf-8",
        description="Text encoding for decoding stdout/stderr (errors replaced)",
    )
    shell: bool = Field(
        default=True,
        description="Execute via system shell; keep True unless you know what you're doing",
    )


_OS_DESC = (
    f"System context: system={platform.system()} {platform.release()}"
    f", machine={platform.machine()}, python={platform.python_version()}"
    f", shell={_detect_shell() or 'unknown'}"
)


class RunCommandTool(BaseTool):  # type: ignore[override]
    name: str = "run_command"
    description: str = (
        "Execute an operating system command and return stdout, stderr, exit code,"
        " duration, and environment context. " + _OS_DESC
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = RunCommandArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        args = RunCommandArgs(**kwargs)

        # Resolve and validate cwd if provided
        cwd_path: Path | None = None
        if args.cwd:
            try:
                cwd_path = Path(args.cwd).expanduser().resolve()
                if not cwd_path.exists() or not cwd_path.is_dir():
                    return {
                        "type": "run_command_error",
                        "error": f"Working directory not found: {cwd_path}",
                        "error_type": "NotADirectoryError",
                        "os": _os_context(),
                    }
            except Exception as e:
                return {
                    "type": "run_command_error",
                    "error": f"Invalid working directory: {str(e)}",
                    "error_type": type(e).__name__,
                    "os": _os_context(),
                }

        env = None
        if args.env:
            # Merge with current environment
            env = os.environ.copy()
            env.update({str(k): str(v) for k, v in args.env.items()})

        # Start the process
        start = time.perf_counter()
        try:
            if args.shell:
                # When using shell=True, pass a single string command
                cmd = args.command
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd_path) if cwd_path else None,
                    env=env,
                )
            else:
                # Without shell, split command into argv using shlex (POSIX); on Windows, shlex is still acceptable for simple cases
                # Convert to argv list
                if os.name == "nt":
                    # On Windows, if user provided quotes, shlex.split with posix=False preserves quoting rules better
                    argv = shlex.split(args.command, posix=False)
                else:
                    argv = shlex.split(args.command, posix=True)
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd_path) if cwd_path else None,
                    env=env,
                )

            try:
                out_b, err_b = await asyncio.wait_for(
                    proc.communicate(), timeout=float(args.timeout)
                )
                exit_code = proc.returncode
            except TimeoutError:
                # Kill and collect any partial output
                try:
                    proc.kill()
                except Exception:
                    pass
                # Attempt to read any pending output briefly
                out_b, err_b = (b"", b"")
                try:
                    out_b, err_b = await asyncio.wait_for(
                        proc.communicate(), timeout=1.0
                    )
                except Exception:
                    pass
                duration_ms = int((time.perf_counter() - start) * 1000)
                return {
                    "type": "run_command_timeout",
                    "command": args.command,
                    "cwd": str(cwd_path) if cwd_path else None,
                    "stdout": out_b.decode(args.encoding, errors="replace")[
                        : args.max_output_bytes
                    ],
                    "stderr": err_b.decode(args.encoding, errors="replace")[
                        : args.max_output_bytes
                    ],
                    "exit_code": None,
                    "timed_out": True,
                    "duration_ms": duration_ms,
                    "os": _os_context(),
                }

            duration_ms = int((time.perf_counter() - start) * 1000)

            # Decode and truncate if needed
            def _decode_and_truncate(b: bytes) -> tuple[str, bool, int]:
                s = b.decode(args.encoding, errors="replace")
                if (
                    len(s.encode(args.encoding, errors="replace"))
                    <= args.max_output_bytes
                ):
                    return s, False, 0
                # Truncate conservatively by characters
                truncated = s.encode(args.encoding, errors="replace")[
                    : args.max_output_bytes
                ]
                s2 = truncated.decode(args.encoding, errors="replace")
                return s2, True, len(b) - len(truncated)

            stdout_text, stdout_trunc, stdout_trunc_bytes = _decode_and_truncate(out_b)
            stderr_text, stderr_trunc, stderr_trunc_bytes = _decode_and_truncate(err_b)

            return {
                "type": "run_command_result",
                "command": args.command,
                "cwd": str(cwd_path) if cwd_path else None,
                "exit_code": exit_code,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "stdout_truncated": stdout_trunc,
                "stderr_truncated": stderr_trunc,
                "stdout_truncated_bytes": stdout_trunc_bytes,
                "stderr_truncated_bytes": stderr_trunc_bytes,
                "timed_out": False,
                "duration_ms": duration_ms,
                "os": _os_context(),
            }

        except FileNotFoundError as e:
            # Command not found (common on Windows or missing binaries)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return {
                "type": "run_command_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "command": args.command,
                "cwd": str(cwd_path) if cwd_path else None,
                "duration_ms": duration_ms,
                "os": _os_context(),
            }
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return {
                "type": "run_command_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "command": args.command,
                "cwd": str(cwd_path) if cwd_path else None,
                "duration_ms": duration_ms,
                "os": _os_context(),
            }
