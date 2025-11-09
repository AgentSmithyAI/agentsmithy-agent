"""Tests for /health endpoint."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentsmithy.api.app import create_app
from agentsmithy.core.project import set_workspace


@pytest.fixture
def temp_workspace():
    """Create temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)
        workspace = set_workspace(workdir)
        yield workspace


@pytest.fixture
def client(temp_workspace):
    """Create test client."""
    app = create_app()
    return TestClient(app)


def write_status(workspace, status_data: dict):
    """Helper to write status.json."""
    status_file = workspace.root_state_dir / "status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(status_data))


def test_health_endpoint_basic(client, temp_workspace):
    """Test basic health endpoint response."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "agentsmithy-server"


def test_health_endpoint_with_ready_status(client, temp_workspace):
    """Test health endpoint with ready server status."""
    write_status(
        temp_workspace,
        {
            "server_status": "ready",
            "server_pid": 12345,
            "port": 8765,
        },
    )

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["server_status"] == "ready"
    assert data["port"] == 8765
    assert data["pid"] is not None  # Current test process PID


def test_health_endpoint_with_error_status(client, temp_workspace):
    """Test health endpoint with error server status."""
    write_status(
        temp_workspace,
        {
            "server_status": "error",
            "server_error": "Configuration validation failed",
        },
    )

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["server_status"] == "error"
    assert data["server_error"] == "Configuration validation failed"


def test_health_endpoint_with_crashed_status(client, temp_workspace):
    """Test health endpoint with crashed server status."""
    write_status(
        temp_workspace,
        {
            "server_status": "crashed",
            "server_error": "Server process terminated unexpectedly",
        },
    )

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["server_status"] == "crashed"
    assert data["server_error"] == "Server process terminated unexpectedly"


def test_health_endpoint_with_starting_status(client, temp_workspace):
    """Test health endpoint with starting server status."""
    write_status(
        temp_workspace,
        {
            "server_status": "starting",
            "server_pid": 12345,
            "port": 8765,
        },
    )

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["server_status"] == "starting"
    assert data["port"] == 8765


def test_health_endpoint_no_status_file(client, temp_workspace):
    """Test health endpoint when status.json doesn't exist."""
    # Don't write status file
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["server_status"] is None  # No status file = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
