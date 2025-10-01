from __future__ import annotations

import sys

import pytest

from agentsmithy_server.tools.builtin.run_command import RunCommandTool

pytestmark = pytest.mark.asyncio


async def _run(tool, **kwargs):
    return await tool.arun(kwargs)


async def test_run_command_stdout_stderr_and_exit_code():
    t = RunCommandTool()
    # Cross-platform: invoke current Python to emit to stdout/stderr and exit with code 3
    cmd = (
        f'{sys.executable} -c "import sys; print(\\"OUT\\"); '
        f'sys.stderr.write(\\"ERR\\n\\"); sys.exit(3)"'
    )
    res = await _run(t, command=cmd, timeout=10.0)

    assert res["type"] == "run_command_result"
    assert res["exit_code"] == 3
    assert "OUT" in res["stdout"]
    assert "ERR" in res["stderr"]
    assert isinstance(res.get("os"), dict)
    assert res["timed_out"] is False


async def test_run_command_unknown_command_nonzero_exit():
    t = RunCommandTool()
    # Through shell, unknown command should yield a non-zero exit code
    res = await _run(t, command="this_command_should_not_exist_abcxyz")
    assert res["type"] == "run_command_result"
    assert isinstance(res.get("exit_code"), int) and res["exit_code"] != 0


async def test_run_command_timeout():
    t = RunCommandTool()
    cmd = f'{sys.executable} -c "import time; time.sleep(2)"'
    res = await _run(t, command=cmd, timeout=0.2)
    assert res["type"] == "tool_error"
    assert res.get("code") == "timeout"
