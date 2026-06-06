"""Tests for the CLI and pipeline entry point."""

from __future__ import annotations

import argparse
import os

import pytest

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstergram import config
from lobstergram.main import apply_runtime_config, publish_to_telegraph


def test_apply_runtime_config_updates_new_state_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """apply_runtime_config updates message-map and bookmark paths along with others."""
    # Register all mutated config attrs with monkeypatch so they are restored after the test.
    for attr in (
        "RSS_URL",
        "STATE_PATH",
        "MESSAGE_MAP_PATH",
        "BOOKMARKS_PATH",
        "SUBSCRIBERS_PATH",
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
            state_path="custom-state.json",
            message_map_path="custom-message-map.json",
            bookmarks_path="custom-bookmarks.csv",
            subscribers_path="custom-subscribers.json",
            max_items=7,
            timeout=30,
            log_level="debug",
            telegram_retry_attempts=4,
            telegraph_retry_attempts=5,
            inter_message_delay=0.1,
        )
    )
    assert str(config.MESSAGE_MAP_PATH) == "custom-message-map.json"
    assert str(config.BOOKMARKS_PATH) == "custom-bookmarks.csv"


def test_publish_to_telegraph_prints_links(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def _fake_build_item_message(item: object) -> tuple[str, dict[str, str]]:
        url = item.link  # type: ignore[attr-defined]
        return "", {"telegraph_link": f"https://telegra.ph/{url.rsplit('/', 1)[-1]}"}

    monkeypatch.setattr("lobstergram.main.build_item_message", _fake_build_item_message)

    rc = publish_to_telegraph(["https://example.com/one", "https://example.com/two"])
    out = capsys.readouterr().out.strip().splitlines()

    assert rc == 0
    assert out == ["https://telegra.ph/one", "https://telegra.ph/two"]


def test_publish_to_telegraph_wraps_failed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_item: object) -> tuple[str, dict[str, str]]:
        raise ValueError("boom")

    monkeypatch.setattr("lobstergram.main.build_item_message", _boom)

    with pytest.raises(RuntimeError, match=r"Failed to process URL: https://example\.com/fail"):
        publish_to_telegraph(["https://example.com/fail"])
