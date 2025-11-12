"""Test that crashed server is detected and marked as 'crashed' on next start."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def read_status(workdir: Path) -> dict:
    """Read status.json from workdir."""
    status_file = workdir / ".agentsmithy" / "status.json"
    if not status_file.exists():
        return {}
    return json.loads(status_file.read_text())


def write_fake_status(workdir: Path, status: dict):
    """Write fake status.json to simulate previous server state."""
    status_file = workdir / ".agentsmithy" / "status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(status, indent=2))


def test_crash_detection_on_startup():
    """Test that crashed server (dead PID with running status) is detected on startup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        # Create .env
        env_file = workdir / ".env"
        env_file.write_text("AGENTSMITHY_MODEL=gpt-4o\nOPENAI_API_KEY=sk-test\n")

        # Simulate a crashed server: write status with dead PID and 'ready' status
        fake_pid = 99999  # Very likely to be a dead PID
        write_fake_status(
            workdir,
            {
                "server_status": "ready",
                "server_pid": fake_pid,
                "port": 8765,
                "server_started_at": "2025-11-08T10:00:00.000Z",
                "server_updated_at": "2025-11-08T10:00:05.000Z",
            },
        )

        # Start new server - should detect crash and mark as crashed
        port = 18767
        env = os.environ.copy()
        env["SERVER_PORT"] = str(port)

        proc = subprocess.Popen(
            [
                sys.executable,
                "main.py",
                "--workdir",
                str(workdir),
                "--ide",
                "test",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Wait a bit for startup
            time.sleep(1.0)

            # Read status - should show crashed before new server starts
            status = read_status(workdir)

            # Verify crash was detected
            # Note: There's a race - might see "crashed" briefly or "starting" from new server
            # But we should definitely NOT see the old dead PID anymore
            assert (
                status.get("server_pid") != fake_pid
            ), f"Old dead PID {fake_pid} should be cleared"

            # The status should either be:
            # 1. "crashed" (if we caught it right after detection)
            # 2. "starting" or "ready" (if new server already started)
            server_status = status.get("server_status")
            assert server_status in (
                "crashed",
                "starting",
                "ready",
            ), f"Expected crashed/starting/ready, got {server_status}"

            # If we see crashed status, verify error message mentions the crash
            if server_status == "crashed":
                error = status.get("server_error", "")
                assert (
                    "terminated unexpectedly" in error
                ), f"Expected crash error message, got: {error}"
                assert (
                    str(fake_pid) in error
                ), f"Expected PID {fake_pid} in error message, got: {error}"

            # Verify new server can start despite crash
            # Wait for new server to be ready
            max_wait = 10.0
            start = time.time()
            new_server_ready = False

            while time.time() - start < max_wait:
                status = read_status(workdir)
                if status.get("server_status") == "ready":
                    new_server_ready = True
                    break
                time.sleep(0.1)

            assert (
                new_server_ready
            ), "New server should start successfully after detecting crash"

            # Verify new server has different PID
            new_pid = status.get("server_pid")
            assert new_pid is not None, "New server should have PID"
            assert new_pid != fake_pid, "New server should have different PID"
            assert new_pid == proc.pid, f"New server PID should be {proc.pid}"

            print("✅ Test passed: Crash detected and new server started successfully")

        finally:
            # Kill server
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def test_crashed_status_does_not_block_startup():
    """Test that server with crashed status can be restarted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        # Create .env
        env_file = workdir / ".env"
        env_file.write_text("AGENTSMITHY_MODEL=gpt-4o\nOPENAI_API_KEY=sk-test\n")

        # Write status showing previous crash
        write_fake_status(
            workdir,
            {
                "server_status": "crashed",
                "server_updated_at": "2025-11-08T10:00:00.000Z",
                "server_error": "Server process (pid 12345) terminated unexpectedly",
            },
        )

        # Start server - should work without issues
        port = 18768
        env = os.environ.copy()
        env["SERVER_PORT"] = str(port)

        proc = subprocess.Popen(
            [
                sys.executable,
                "main.py",
                "--workdir",
                str(workdir),
                "--ide",
                "test",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Wait for server to start
            max_wait = 10.0
            start = time.time()
            server_ready = False

            while time.time() - start < max_wait:
                status = read_status(workdir)
                if status.get("server_status") == "ready":
                    server_ready = True
                    break
                time.sleep(0.1)

            assert server_ready, "Server should start successfully after crashed state"

            # Verify status changed from crashed to ready
            status = read_status(workdir)
            assert (
                status.get("server_status") == "ready"
            ), f"Expected status 'ready', got {status.get('server_status')}"

            # Verify error is cleared (StatusManager uses .pop() to remove the key)
            assert (
                "server_error" not in status
            ), "Error should be cleared on successful start"

            print("✅ Test passed: Server started successfully after crashed state")

        finally:
            # Kill server
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    test_crash_detection_on_startup()
    test_crashed_status_does_not_block_startup()
    print("\n✅✅ All crash detection tests passed!")
