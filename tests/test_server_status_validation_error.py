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
    """Test that server_status='error' with error when validation fails."""
    # Create temp workdir
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)

        # Create .env WITHOUT API key - will fail validation
        env_file = workdir / ".env"
        env_file.write_text("AGENTSMITHY_MODEL=gpt-4o\n")  # No API key!

        # Start server process - should fail validation
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
            # Wait for process to exit (should fail fast)
            exit_code = proc.wait(timeout=10)

            # Should exit with error code
            assert exit_code != 0, f"Expected non-zero exit code, got {exit_code}"

            # Check status file was created with error state
            status = read_status(workdir)
            assert status.get("server_status") == "error", (
                f"Expected server_status='error' after validation error, "
                f"got: {status.get('server_status')}"
            )

            assert "server_error" in status, "Expected server_error in status"
            assert (
                "Configuration validation failed" in status["server_error"]
                or "API key" in status["server_error"]
            ), f"Expected validation error message, got: {status.get('server_error')}"

            print(
                "✅ Test passed: server_status='error' with error message on validation failure"
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
