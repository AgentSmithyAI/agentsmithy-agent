"""Test that server_status is set to 'error' with error when validation fails."""

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


def read_status(workdir: Path) -> dict:
    """Read status.json from workdir."""
    status_file = workdir / ".agentsmithy" / "status.json"
    if not status_file.exists():
        return {}
    import json

    return json.loads(status_file.read_text())


def test_server_status_validation_error():
    """Test that server starts with warning when validation fails (soft validation)."""
    # Create temp workdir
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        # Create .env WITHOUT API key - will produce validation warning but server starts
        env_file = workdir / ".env"
        env_file.write_text("AGENTSMITHY_MODEL=gpt-4o\n")  # No API key!

        # Start server process - should start despite validation warning
        port = 18766  # Different port
        env = os.environ.copy()
        env["SERVER_PORT"] = str(port)
        # Remove API key from environment too
        env.pop("OPENAI_API_KEY", None)

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
            # Wait for server to start (should succeed now with soft validation)
            import time

            time.sleep(3)  # Give server time to start

            # Server should be running
            assert proc.poll() is None, "Server should still be running"

            # Check status file shows ready (not error)
            status = read_status(workdir)
            # Server should be in 'ready' state, not 'error'
            # (validation is soft - just a warning)
            assert status.get("server_status") in ["ready", "starting"], (
                f"Expected server_status='ready' or 'starting' with soft validation, "
                f"got: {status.get('server_status')}"
            )

            print(
                "✅ Test passed: server starts successfully with soft validation (missing API key)"
            )

        finally:
            # Cleanup process if still running
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    test_server_status_validation_error()
