"""Test that server_status is set to 'ready' only after server starts listening."""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Wait for a port to start listening."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex((host, port))
                if result == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def read_status(workdir: Path) -> dict:
    """Read status.json from workdir."""
    status_file = workdir / ".agentsmithy" / "status.json"
    if not status_file.exists():
        return {}
    import json

    return json.loads(status_file.read_text())


def test_server_status_ready_after_listening():
    """Test that server_status='ready' is only set after server is listening."""
    # Create temp workdir
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        # Create minimal .env
        env_file = workdir / ".env"
        env_file.write_text("AGENTSMITHY_MODEL=gpt-4o\nOPENAI_API_KEY=sk-test\n")

        # Start server process
        port = 18765  # Non-standard port to avoid conflicts
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
            # Wait for status file to be created with "starting"
            max_wait = 5.0
            start = time.time()
            status_before = {}
            while time.time() - start < max_wait:
                status_before = read_status(workdir)
                if status_before.get("server_status") == "starting":
                    break
                time.sleep(0.1)

            assert status_before.get("server_status") == "starting", (
                f"Expected server_status='starting' before port listens, "
                f"got: {status_before.get('server_status')}"
            )

            # Wait for port to start listening
            port_ok = wait_for_port("127.0.0.1", port, timeout=10.0)

            # If port didn't start, print stderr for debugging
            if not port_ok:
                stdout, stderr = proc.communicate(timeout=1)
                print("=== STDOUT ===")
                print(stdout)
                print("=== STDERR ===")
                print(stderr)
                raise AssertionError("Server port never started listening")

            # Give a moment for status to update
            time.sleep(0.2)

            # Check status after port is listening
            status_after = read_status(workdir)
            assert status_after.get("server_status") == "ready", (
                f"Expected server_status='ready' after port listens, "
                f"got: {status_after.get('server_status')}"
            )

            print("✅ Test passed: server_status='ready' only after port listening")

        finally:
            # Kill server
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    test_server_status_ready_after_listening()
