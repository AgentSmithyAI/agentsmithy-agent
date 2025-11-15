"""Tests for platform-specific path normalization."""

from agentsmithy.platforms.posix import PosixAdapter
from agentsmithy.platforms.windows import WindowsAdapter


def test_posix_normalize_path():
    """POSIX adapter should return paths as-is (already using forward slashes)."""
    adapter = PosixAdapter()
    assert adapter.normalize_path("path/to/file.txt") == "path/to/file.txt"
    assert adapter.normalize_path("src/main.py") == "src/main.py"
    # Backslashes are valid filename characters on POSIX, not path separators
    assert adapter.normalize_path("weird\\name.txt") == "weird\\name.txt"


def test_windows_normalize_path():
    """Windows adapter should convert backslashes to forward slashes."""
    adapter = WindowsAdapter()
    assert adapter.normalize_path("path\\to\\file.txt") == "path/to/file.txt"
    assert adapter.normalize_path("C:\\Users\\user\\project") == "C:/Users/user/project"
    assert adapter.normalize_path("src\\main.py") == "src/main.py"
    # Already normalized paths should remain unchanged
    assert adapter.normalize_path("path/to/file.txt") == "path/to/file.txt"
    # Mixed paths should be fully normalized
    assert (
        adapter.normalize_path("path\\to/mixed\\slashes.txt")
        == "path/to/mixed/slashes.txt"
    )


def test_normalize_path_function_uses_current_os():
    """Test that global normalize_path function uses system's adapter."""
    import os

    from agentsmithy.platforms import normalize_path

    # On POSIX systems, paths remain unchanged
    # On Windows, backslashes would be converted
    if os.name == "nt":
        assert normalize_path("path\\to\\file.txt") == "path/to/file.txt"
    else:
        assert normalize_path("path/to/file.txt") == "path/to/file.txt"


def test_empty_path():
    """Test handling of empty paths."""
    posix_adapter = PosixAdapter()
    windows_adapter = WindowsAdapter()
    assert posix_adapter.normalize_path("") == ""
    assert windows_adapter.normalize_path("") == ""


def test_root_paths():
    """Test handling of root paths."""
    windows_adapter = WindowsAdapter()
    assert windows_adapter.normalize_path("C:\\") == "C:/"
    assert windows_adapter.normalize_path("\\\\server\\share") == "//server/share"


def test_posix_global_config_dir_with_xdg(monkeypatch, tmp_path):
    adapter = PosixAdapter()
    xdg_dir = tmp_path / "xdg_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_dir))
    path = adapter.get_global_config_dir("AgentSmithy")
    assert path == xdg_dir / "agentsmithy"


def test_posix_global_config_dir_macos(monkeypatch, tmp_path):
    adapter = PosixAdapter()
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "darwin", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    path = adapter.get_global_config_dir("AgentSmithy")
    assert path == tmp_path / "Library" / "Application Support" / "AgentSmithy"


def test_windows_global_config_dir(monkeypatch, tmp_path):
    adapter = WindowsAdapter()
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    path = adapter.get_global_config_dir("AgentSmithy")
    assert path == appdata / "AgentSmithy"
