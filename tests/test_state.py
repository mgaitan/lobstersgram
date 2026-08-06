"""Tests for persistent state helpers (state, message map, bookmarks)."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstersgram.state import (
    load_bookmarks,
    load_message_map,
    save_bookmarks,
    save_message_map,
    sync_bookmark_rows,
    update_message_map,
)

_ARTICLE_LINKS = {
    "telegraph_link": "https://telegra.ph/test-article",
    "article_link": "https://example.com/article",
    "discussion_link": "https://lobste.rs/s/abc123",
    "title": "Test Article",
}

# ---------------------------------------------------------------------------
# message_map tests
# ---------------------------------------------------------------------------


def test_load_message_map_returns_empty_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_message_map returns an empty dict when the file does not exist."""
    monkeypatch.chdir(tmp_path)
    assert load_message_map() == {}


def test_save_and_load_message_map_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_message_map followed by load_message_map returns the same data."""
    monkeypatch.chdir(tmp_path)
    msg_map = {"123:456": _ARTICLE_LINKS}
    save_message_map(msg_map)
    assert load_message_map() == msg_map


def test_update_message_map_adds_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update_message_map writes new chat_id:message_id keys."""
    monkeypatch.chdir(tmp_path)
    update_message_map({111: 42, 222: 99}, _ARTICLE_LINKS)
    stored = load_message_map()
    assert stored["111:42"] == _ARTICLE_LINKS
    assert stored["222:99"] == _ARTICLE_LINKS


def test_update_message_map_noop_on_empty_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update_message_map does nothing when sent dict is empty."""
    monkeypatch.chdir(tmp_path)
    update_message_map({}, _ARTICLE_LINKS)
    assert not (tmp_path / "message_map.json").exists()


# ---------------------------------------------------------------------------
# bookmark sync tests
# ---------------------------------------------------------------------------

_BOOKMARK_ROW: dict[str, str] = {
    "telegraph_link": "https://telegra.ph/test-article",
    "article_link": "https://example.com/article",
    "discussion_link": "https://lobste.rs/s/abc123",
    "username": "alice",
    "user_id": "789",
    "emojis": "👍",
    "reacted_at": "2024-01-01T00:00:00+00:00",
}


def test_save_bookmarks_creates_csv_with_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_bookmarks creates the CSV file with a header row."""
    monkeypatch.chdir(tmp_path)
    save_bookmarks([_BOOKMARK_ROW])
    csv_text = (tmp_path / "bookmark.csv").read_text(encoding="utf-8")
    assert "telegraph_link" in csv_text
    assert "alice" in csv_text


def test_load_bookmarks_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_bookmarks returns the rows previously written by save_bookmarks."""
    monkeypatch.chdir(tmp_path)
    row2 = {**_BOOKMARK_ROW, "username": "bob"}
    save_bookmarks([_BOOKMARK_ROW, row2])
    assert load_bookmarks() == [_BOOKMARK_ROW, row2]


def test_load_bookmarks_missing_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_bookmarks returns an empty list when the CSV file is absent."""
    monkeypatch.chdir(tmp_path)
    assert load_bookmarks() == []


def test_save_bookmarks_csv_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CSV produced by save_bookmarks contains all expected columns."""
    monkeypatch.chdir(tmp_path)
    save_bookmarks([_BOOKMARK_ROW])
    with (tmp_path / "bookmark.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["username"] == "alice"
    assert rows[0]["emojis"] == "👍"
    assert rows[0]["telegraph_link"] == "https://telegra.ph/test-article"


def test_sync_bookmark_rows_replaces_existing_reaction() -> None:
    """A reaction edit replaces the existing row for the same subscriber/article."""
    updated_row = {**_BOOKMARK_ROW, "emojis": "🔥"}
    synced, changed = sync_bookmark_rows([_BOOKMARK_ROW], [updated_row])
    assert synced == [updated_row]
    assert changed is True


def test_sync_bookmark_rows_removes_existing_reaction() -> None:
    """An empty-emoji update removes the existing bookmark row."""
    removal_row = {**_BOOKMARK_ROW, "emojis": ""}
    synced, changed = sync_bookmark_rows([_BOOKMARK_ROW], [removal_row])
    assert synced == []
    assert changed is True
