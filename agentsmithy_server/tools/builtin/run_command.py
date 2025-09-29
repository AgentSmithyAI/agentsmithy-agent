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

from agentsmithy_server.utils.logger import agent_logger

from ..base_tool import BaseTool


def _detect_shell() -> str | None:
    """Detect the preferred system shell executable.

    Resolution strategy:
    - Windows: return COMSPEC if set, otherwise 'cmd.exe'.
    - POSIX (Linux/macOS/BSD): return SHELL if set.
      If SHELL is unset on macOS (Darwin), prefer '/bin/zsh' (default since 10.15),
      then '/bin/bash' if available, else fall back to '/bin/sh'.
      On other POSIX systems, fall back to '/bin/sh'.

    Returns:
        Path to the shell executable as a string, or None if detection fails.
        Note: with current fallbacks this function typically returns a string.
    """
    # Prefer explicit environment variables
    if os.name == "nt":
        return os.environ.get("COMSPEC") or "cmd.exe"

    shell = os.environ.get("SHELL")
    if shell:
        return shell

    # Platform-specific sensible defaults
    if sys.platform == "darwin":  # macOS
        for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
            if Path(candidate).exists():
                return candidate
        return "/bin/sh"

    # Generic POSIX fallback
    return "/bin/sh"


def _os_context() -> dict[str, Any]:
    """Collect a snapshot of OS and runtime context for diagnostics.

    Returns a mapping with keys such as:
    - platform, system, release, version, machine, python, shell, and optionally processor.

    The function is defensive and never raises; it returns an empty dict on failure.
    """
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


class RunCommandTool(BaseTool):
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
                # Build argv for shell=False
                if os.name == "nt":
                    argv_tmp = shlex.split(args.command, posix=False)
                else:
                    argv_tmp = shlex.split(args.command, posix=True)

                # Detect Python executable and '-c' usage based on argv_tmp, but reconstruct code from the original string
                is_python = False
                try:
                    exe_base = Path(argv_tmp[0]).name.lower() if argv_tmp else ""
                    is_python = (
                        exe_base.startswith("python")
                        or exe_base == Path(sys.executable).name.lower()
                    )
                except Exception:
                    is_python = False

                if is_python and "-c" in argv_tmp:
                    # Locate '-c' in the original string and keep everything after it as a single code argument
                    try:
                        c_pos = args.command.index("-c")
                    except ValueError:
                        c_pos = -1
                    if c_pos != -1:
                        j = c_pos + 2
                        # Skip following whitespace
                        while j < len(args.command) and args.command[j].isspace():
                            j += 1
                        prefix = args.command[:j].strip()
                        code_str = args.command[j:]
                        # Normalize accidental literal newlines in code string to escaped form for Python -c
                        if "\n" in code_str:
                            code_str = code_str.replace("\n", r"\n")
                        # Parse prefix (up to and including -c) to argv, then append code verbatim
                        if os.name == "nt":
                            prefix_argv = shlex.split(prefix, posix=False)
                        else:
                            prefix_argv = shlex.split(prefix, posix=True)
                        argv = prefix_argv + [code_str]
                    else:
                        # Fallback: join the remainder tokens after '-c' (may lose quotes, but last resort)
                        c_index = argv_tmp.index("-c")
                        argv = argv_tmp[: c_index + 1] + [
                            " ".join(argv_tmp[c_index + 1 :])
                        ]
                else:
                    argv = argv_tmp

                agent_logger.debug("run_command exec", argv=argv, shell=args.shell)
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
                try:
                    agent_logger.debug("run_command done", exit_code=exit_code)
                except Exception:
                    pass
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
                    "stdout": out_b[: args.max_output_bytes].decode(
                        args.encoding, errors="replace"
                    ),
                    "stderr": err_b[: args.max_output_bytes].decode(
                        args.encoding, errors="replace"
                    ),
                    "exit_code": None,
                    "timed_out": True,
                    "duration_ms": duration_ms,
                    "os": _os_context(),
                }

            duration_ms = int((time.perf_counter() - start) * 1000)

            # Decode and truncate if needed
            def _decode_and_truncate(b: bytes) -> tuple[str, bool, int]:
                """Decode a bytes buffer and enforce a byte-size limit.

                Args:
                    b: Raw bytes from a stream (stdout/stderr).

                Returns:
                    A tuple of:
                    - decoded string using args.encoding with replacement for errors,
                    - was_truncated flag (True if the original bytes exceeded the limit),
                    - number of bytes truncated from the original buffer.
                """
                # Fast path: no truncation needed
                if len(b) <= args.max_output_bytes:
                    s = b.decode(args.encoding, errors="replace")
                    return s, False, 0
                # Truncate by bytes to avoid re-encoding overhead; decode with replacement to handle partial characters
                truncated_b = b[: args.max_output_bytes]
                s2 = truncated_b.decode(args.encoding, errors="replace")
                truncated_bytes = len(b) - len(truncated_b)
                return s2, True, truncated_bytes

            stdout_text, stdout_trunc, stdout_trunc_bytes = _decode_and_truncate(out_b)
            stderr_text, stderr_trunc, stderr_trunc_bytes = _decode_and_truncate(err_b)

            try:
                agent_logger.debug(
                    "run_command outputs", stdout=stdout_text, stderr=stderr_text
                )
            except Exception:
                pass

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
