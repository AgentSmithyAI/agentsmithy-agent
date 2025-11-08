"""Test .env file loading from workdir."""

import os
import tempfile
from pathlib import Path


def test_dotenv_loading_from_workdir():
    """Test that .env file is loaded from workdir on startup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)
        env_file = workdir / ".env"

        # Create .env file with test variables
        env_file.write_text(
            "TEST_OPENAI_API_KEY=sk-test-key-123\n"
            "TEST_MODEL=gpt-4o\n"
            "TEST_SERVER_PORT=9999\n"
        )

        # Save original env state
        original_env = {
            "TEST_OPENAI_API_KEY": os.environ.get("TEST_OPENAI_API_KEY"),
            "TEST_MODEL": os.environ.get("TEST_MODEL"),
            "TEST_SERVER_PORT": os.environ.get("TEST_SERVER_PORT"),
        }

        try:
            # Clear test variables if they exist
            for key in original_env.keys():
                os.environ.pop(key, None)

            # Import and use load_dotenv directly (simulating main.py behavior)
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_file, override=False)

            # Verify variables were loaded
            assert os.environ.get("TEST_OPENAI_API_KEY") == "sk-test-key-123"
            assert os.environ.get("TEST_MODEL") == "gpt-4o"
            assert os.environ.get("TEST_SERVER_PORT") == "9999"

        finally:
            # Restore original environment
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def test_dotenv_does_not_override_existing_vars():
    """Test that .env does not override existing environment variables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)
        env_file = workdir / ".env"

        # Create .env file
        env_file.write_text("TEST_OVERRIDE_VAR=from-env-file\n")

        # Set variable before loading .env
        original_value = os.environ.get("TEST_OVERRIDE_VAR")
        os.environ["TEST_OVERRIDE_VAR"] = "already-set"

        try:
            from dotenv import load_dotenv

            # Load with override=False (default behavior in main.py)
            load_dotenv(dotenv_path=env_file, override=False)

            # Should keep the already-set value
            assert os.environ.get("TEST_OVERRIDE_VAR") == "already-set"

        finally:
            # Restore
            if original_value is None:
                os.environ.pop("TEST_OVERRIDE_VAR", None)
            else:
                os.environ["TEST_OVERRIDE_VAR"] = original_value


def test_dotenv_missing_file_handled_gracefully():
    """Test that missing .env file is handled without errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = Path(tmpdir)
        env_file = workdir / ".env"

        # Ensure .env does not exist
        assert not env_file.exists()

        # This should not raise an error (simulating main.py behavior)
        from dotenv import load_dotenv

        # load_dotenv returns False when file doesn't exist, but doesn't raise
        result = load_dotenv(dotenv_path=env_file, override=False)
        assert result is False  # File not found, but no error
