"""Unit tests for StatusManager."""

import json
import tempfile
from pathlib import Path

from agentsmithy.core.status_manager import StatusManager


def test_status_manager_server_status_starting():
    """Test setting server status to starting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        manager.update_server_status("starting", pid=12345, port=8765)

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "starting"
        assert status["server_pid"] == 12345
        assert status["port"] == 8765
        assert "server_started_at" in status
        assert "server_updated_at" in status
        assert "server_error" not in status


def test_status_manager_server_status_ready():
    """Test setting server status to ready."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First starting
        manager.update_server_status("starting", pid=12345, port=8765)

        # Then ready
        manager.update_server_status("ready")

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "ready"
        assert status["server_pid"] == 12345  # Preserved
        assert status["port"] == 8765  # Preserved
        assert "server_error" not in status  # Cleared on ready


def test_status_manager_server_status_error():
    """Test setting server status to error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First starting
        manager.update_server_status("starting", pid=12345, port=8765)

        # Then error
        manager.update_server_status("error", error="Test error message")

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "error"
        assert "server_pid" not in status  # Cleared
        assert "port" not in status  # Cleared
        assert status["server_error"] == "Test error message"


def test_status_manager_server_status_crashed():
    """Test setting server status to crashed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First starting
        manager.update_server_status("starting", pid=12345, port=8765)

        # Then crashed
        manager.update_server_status("crashed", error="Unexpected termination")

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "crashed"
        assert "server_pid" not in status  # Cleared
        assert "port" not in status  # Cleared
        assert status["server_error"] == "Unexpected termination"


def test_status_manager_server_status_stopped():
    """Test setting server status to stopped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First starting
        manager.update_server_status("starting", pid=12345, port=8765)

        # Then stopped
        manager.update_server_status("stopped")

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "stopped"
        assert "server_pid" not in status  # Cleared
        assert "port" not in status  # Cleared
        assert "server_started_at" not in status  # Cleared
        assert "server_error" not in status  # Cleared


def test_status_manager_server_status_stopping():
    """Test setting server status to stopping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First ready with error from previous state
        manager.update_server_status("ready", pid=12345, port=8765)
        # Manually add error to test it gets cleared
        status = json.loads(status_path.read_text())
        status["server_error"] = "Old error"
        status_path.write_text(json.dumps(status))

        # Then stopping
        manager.update_server_status("stopping")

        status = json.loads(status_path.read_text())
        assert status["server_status"] == "stopping"
        assert "server_error" not in status  # Cleared on stopping


def test_status_manager_scan_status_scanning():
    """Test setting scan status to scanning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        manager.update_scan_status(
            "scanning", progress=50, pid=99999, task_id="task-123"
        )

        status = json.loads(status_path.read_text())
        assert status["scan_status"] == "scanning"
        assert status["scan_progress"] == 50
        assert status["scan_pid"] == 99999
        assert status["scan_task_id"] == "task-123"
        assert "scan_started_at" in status
        assert "scan_updated_at" in status


def test_status_manager_scan_status_done():
    """Test setting scan status to done."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # First scanning
        manager.update_scan_status("scanning", progress=0)

        # Then done
        manager.update_scan_status("done", progress=100)

        status = json.loads(status_path.read_text())
        assert status["scan_status"] == "done"
        assert status["scan_progress"] == 100
        assert "error" not in status  # Cleared on success


def test_status_manager_scan_status_error():
    """Test setting scan status to error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        manager.update_scan_status("error", error="Scan failed")

        status = json.loads(status_path.read_text())
        assert status["scan_status"] == "error"
        assert status["error"] == "Scan failed"


def test_status_manager_scan_progress_bounds():
    """Test that scan progress is bounded to 0-100."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # Test negative
        manager.update_scan_status("scanning", progress=-10)
        status = json.loads(status_path.read_text())
        assert status["scan_progress"] == 0

        # Test over 100
        manager.update_scan_status("scanning", progress=150)
        status = json.loads(status_path.read_text())
        assert status["scan_progress"] == 100


def test_status_manager_get_status():
    """Test get_status method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # Need starting first to set PID/port
        manager.update_server_status("starting", pid=12345, port=8765)
        manager.update_server_status("ready")

        status = manager.get_status()
        assert status["server_status"] == "ready"
        assert status["server_pid"] == 12345  # Preserved from starting
        assert status["port"] == 8765  # Preserved from starting


def test_status_manager_empty_file():
    """Test reading from non-existent file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # Should return empty dict
        status = manager.get_status()
        assert status == {}


def test_status_manager_atomic_writes():
    """Test that writes are atomic (temp file + rename)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        manager.update_server_status("starting", pid=12345, port=8765)

        # Verify temp file doesn't exist after write
        tmp_file = status_path.with_suffix(".tmp")
        assert not tmp_file.exists()

        # Verify main file exists
        assert status_path.exists()


def test_status_manager_preserves_other_fields():
    """Test that updating one status preserves other fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        status_path = Path(tmpdir) / "status.json"
        manager = StatusManager(status_path)

        # Set server status (starting first to set PID/port)
        manager.update_server_status("starting", pid=12345, port=8765)
        manager.update_server_status("ready")

        # Set scan status
        manager.update_scan_status("scanning", progress=50)

        # Verify both are present
        status = json.loads(status_path.read_text())
        assert status["server_status"] == "ready"
        assert status["server_pid"] == 12345  # Preserved from starting
        assert status["scan_status"] == "scanning"
        assert status["scan_progress"] == 50


if __name__ == "__main__":
    import sys

    # Run all tests
    test_functions = [
        test_status_manager_server_status_starting,
        test_status_manager_server_status_ready,
        test_status_manager_server_status_error,
        test_status_manager_server_status_crashed,
        test_status_manager_server_status_stopped,
        test_status_manager_server_status_stopping,
        test_status_manager_scan_status_scanning,
        test_status_manager_scan_status_done,
        test_status_manager_scan_status_error,
        test_status_manager_scan_progress_bounds,
        test_status_manager_get_status,
        test_status_manager_empty_file,
        test_status_manager_atomic_writes,
        test_status_manager_preserves_other_fields,
    ]

    for test_func in test_functions:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
        except Exception as e:
            print(f"❌ {test_func.__name__}: {e}")
            sys.exit(1)

    print("\n✅ All StatusManager tests passed!")
