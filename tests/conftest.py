"""Pytest configuration and shared fixtures."""

import os
import pytest
import asyncio

# Set test environment variables
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-unit-tests")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_test_dirs(tmp_path, monkeypatch):
    """Override storage directories to use tmp_path in tests."""
    from app.core import config
    from pathlib import Path

    monkeypatch.setattr(config.settings, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config.settings, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(config.settings, "TEMP_DIR", tmp_path / "temp")

    (tmp_path / "uploads").mkdir(parents=True)
    (tmp_path / "outputs").mkdir(parents=True)
    (tmp_path / "temp").mkdir(parents=True)
