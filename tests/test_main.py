"""Tests for the CLI and pipeline entry point."""

from __future__ import annotations

import argparse
import os

import pytest

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstergram import config
from lobstergram.main import apply_runtime_config


def test_apply_runtime_config_updates_new_state_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """apply_runtime_config updates db-path and other settings."""
    # Register all mutated config attrs with monkeypatch so they are restored after the test.
    for attr in (
        "RSS_URL",
        "DB_PATH",
        "MAX_ITEMS_PER_RUN",
        "REQUEST_TIMEOUT",
        "LOG_LEVEL",
        "TELEGRAM_RETRY_ATTEMPTS",
        "TELEGRAPH_RETRY_ATTEMPTS",
        "INTER_MESSAGE_DELAY",
    ):
        monkeypatch.setattr(config, attr, getattr(config, attr))

    apply_runtime_config(
        argparse.Namespace(
            rss_url="https://example.com/rss",
            db_path="custom.db",
            max_items=7,
            timeout=30,
            log_level="debug",
            telegram_retry_attempts=4,
            telegraph_retry_attempts=5,
            inter_message_delay=0.1,
        )
    )
    assert str(config.DB_PATH) == "custom.db"
