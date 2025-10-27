"""Tests for checkpoint ignoring build artifacts across multiple languages.

Verifies that:
1. Build artifacts from Python, Node.js, Java, C/C++, Rust, Go are ignored
2. Important config files (.gitignore, .github, etc.) are tracked
3. Source code is tracked
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from agentsmithy.services.versioning import VersioningTracker


@pytest.fixture
def temp_project():
    """Create a temporary project for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        yield project_root


def get_files_in_checkpoint(tracker: VersioningTracker, commit_id: str) -> list[str]:
    """Get list of files in a checkpoint using git ls-tree."""
    git_dir = tracker.shadow_root / ".git"
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", "ls-tree", "-r", "--name-only", commit_id],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def test_python_artifacts_ignored(temp_project):
    """Test that Python build artifacts are ignored."""
    # Create Python artifacts
    artifacts = {
        "__pycache__/test.pyc": "# cache",
        ".pytest_cache/v/cache/nodeids": "test ids",
        ".mypy_cache/3.9/main.data.json": "{}",
        "dist/package-1.0.tar.gz": "binary",
        "build/lib/mylib.so": "binary",
        "htmlcov/index.html": "<html>",
        ".tox/py39/lib/package.py": "# tox",
    }

    # Create source files
    source_files = {
        "src/main.py": 'print("hello")',
        "tests/test_main.py": "def test(): pass",
        "setup.py": "from setuptools import setup",
        "requirements.txt": "pytest",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_nodejs_artifacts_ignored(temp_project):
    """Test that Node.js build artifacts are ignored."""
    # Create Node.js artifacts
    artifacts = {
        "node_modules/express/index.js": "// dep",
        "node_modules/lodash/package.json": "{}",
        ".next/cache/webpack/client-development.js": "// cache",
        ".nuxt/dist/client.js": "// nuxt",
        "dist/bundle.js": "// bundled",
        "out/index.html": "<html>",
        ".cache/loader.js": "// cache",
    }

    # Create source files
    source_files = {
        "src/index.js": "console.log('hello')",
        "package.json": '{"name": "test"}',
        ".github/workflows/ci.yml": "name: CI",
        ".eslintrc.json": "{}",
        "tsconfig.json": "{}",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_java_artifacts_ignored(temp_project):
    """Test that Java build artifacts are ignored."""
    # Create Java artifacts
    artifacts = {
        "target/classes/com/example/Main.class": "binary",
        "target/test-classes/TestMain.class": "binary",
        "build/libs/app.jar": "binary",
        ".gradle/7.4/checksums/checksums.lock": "binary",
    }

    # Create source files
    source_files = {
        "src/main/java/com/example/Main.java": "public class Main {}",
        "pom.xml": "<project></project>",
        "build.gradle": "plugins { id 'java' }",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_cpp_artifacts_ignored(temp_project):
    """Test that C/C++ build artifacts are ignored."""
    # Create C/C++ artifacts
    artifacts = {
        "main.o": "binary",
        "lib/util.o": "binary",
        "build/main": "binary",
        "cmake-build-debug/CMakeFiles/main.dir/main.cpp.o": "binary",
        "CMakeFiles/3.20.0/CMakeCCompiler.cmake": "# cmake",
    }

    # Create source files
    source_files = {
        "src/main.cpp": "int main() { return 0; }",
        "include/util.h": "#pragma once",
        "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)",
        "Makefile": "all:\n\tgcc main.c",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_rust_go_artifacts_ignored(temp_project):
    """Test that Rust and Go build artifacts are ignored."""
    # Create Rust/Go artifacts
    artifacts = {
        "target/debug/myapp": "binary",
        "target/release/myapp": "binary",
        "vendor/github.com/pkg/errors/errors.go": "// vendored",
    }

    # Create source files
    source_files = {
        "src/main.rs": "fn main() {}",
        "Cargo.toml": "[package]",
        "main.go": "package main",
        "go.mod": "module example.com/app",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_logs_and_temp_files_ignored(temp_project):
    """Test that log files and temporary files are ignored."""
    # Create logs and temp files
    artifacts = {
        "logs/app.log": "log entry",
        "logs/error.log": "error entry",
        "tmp/session.tmp": "temp data",
        "temp/build.tmp": "temp data",
        "debug.log": "debug entry",
        "file.bak": "backup",
        "file.swp": "vim swap",
    }

    # Create source files
    source_files = {
        "src/app.py": "# app",
        "README.md": "# Project",
    }

    # Create all files
    for path, content in {**artifacts, **source_files}.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Artifacts should NOT be tracked
    for artifact_path in artifacts:
        assert (
            artifact_path not in tracked_files
        ), f"Artifact {artifact_path} should be ignored"

    # Source files SHOULD be tracked
    for source_path in source_files:
        assert (
            source_path in tracked_files
        ), f"Source file {source_path} should be tracked"


def test_important_dotfiles_tracked(temp_project):
    """Test that important dotfiles and dot-directories are tracked."""
    # Important config files that SHOULD be tracked
    important_files = {
        ".gitignore": "node_modules/",
        ".github/workflows/ci.yml": "name: CI",
        ".github/workflows/deploy.yml": "name: Deploy",
        ".editorconfig": "[*]\nindent_size = 2",
        ".prettierrc": '{"semi": false}',
        ".eslintrc.json": "{}",
        ".vscode/settings.json": "{}",
        ".idea/workspace.xml": "<xml>",
        "src/main.py": "# source",
    }

    # Create all files
    for path, content in important_files.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # All important files SHOULD be tracked
    for file_path in important_files:
        assert (
            file_path in tracked_files
        ), f"Important file {file_path} should be tracked"


def test_mixed_project_comprehensive(temp_project):
    """Comprehensive test with mixed language project."""
    # Create a realistic multi-language project structure
    files = {
        # Python source
        "backend/app.py": "# backend",
        "backend/requirements.txt": "flask",
        # Python artifacts (should be ignored)
        "backend/__pycache__/app.cpython-39.pyc": "binary",
        "backend/.pytest_cache/README.md": "cache",
        # Node.js source
        "frontend/src/index.js": "// frontend",
        "frontend/package.json": "{}",
        # Node.js artifacts (should be ignored)
        "frontend/node_modules/react/index.js": "// dep",
        "frontend/dist/bundle.js": "// built",
        # Config files (should be tracked)
        ".gitignore": "node_modules/\n__pycache__/",
        ".github/workflows/test.yml": "name: Test",
        "docker-compose.yml": "version: '3'",
        "README.md": "# Project",
        # Logs and temp (should be ignored)
        "logs/app.log": "log",
        "tmp/data.tmp": "temp",
    }

    # Create all files
    for path, content in files.items():
        file = temp_project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    # Create checkpoint
    tracker = VersioningTracker(str(temp_project))
    cp = tracker.create_checkpoint("Initial")

    # Check what was tracked
    tracked_files = get_files_in_checkpoint(tracker, cp.commit_id)

    # Define expected tracked files
    should_track = [
        "backend/app.py",
        "backend/requirements.txt",
        "frontend/src/index.js",
        "frontend/package.json",
        ".gitignore",
        ".github/workflows/test.yml",
        "docker-compose.yml",
        "README.md",
    ]

    should_ignore = [
        "backend/__pycache__/app.cpython-39.pyc",
        "backend/.pytest_cache/README.md",
        "frontend/node_modules/react/index.js",
        "frontend/dist/bundle.js",
        "logs/app.log",
        "tmp/data.tmp",
    ]

    for path in should_track:
        assert path in tracked_files, f"Source/config file {path} should be tracked"

    for path in should_ignore:
        assert path not in tracked_files, f"Artifact {path} should be ignored"
