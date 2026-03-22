"""Tests for lobstergram package helpers."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstergram import config
from lobstergram.cli import apply_runtime_config
from lobstergram.content import make_images_absolute, preprocess_figures
from lobstergram.state import (
    load_bookmarks,
    load_message_map,
    save_bookmarks,
    save_message_map,
    sync_bookmark_rows,
    update_message_map,
)
from lobstergram.telegram import _extract_reaction_row

BASE = "https://example.com/articles/my-post/"

# ---------------------------------------------------------------------------
# make_images_absolute tests (pre-existing)
# ---------------------------------------------------------------------------


def test_absolute_http_src_unchanged() -> None:
    """An already-absolute http:// src is kept as-is."""
    html = '<p><img src="https://cdn.example.com/img.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/img.png"' in result


def test_relative_root_src_becomes_absolute() -> None:
    """A root-relative src (e.g. /images/foo.png) is resolved against base_url."""
    html = '<p><img src="/images/foo.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/images/foo.png"' in result


def test_relative_path_src_becomes_absolute() -> None:
    """A relative path src (e.g. ../img/bar.jpg) is resolved against base_url."""
    html = '<p><img src="../img/bar.jpg"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/articles/img/bar.jpg"' in result


def test_data_uri_image_is_removed() -> None:
    """Images with data: URIs are removed entirely."""
    html = '<p>before</p><p><img src="data:image/png;base64,abc"/></p><p>after</p>'
    result = make_images_absolute(html, BASE)
    assert "<img" not in result
    assert "before" in result
    assert "after" in result


def test_empty_src_image_is_removed() -> None:
    """Images with empty src are removed entirely."""
    html = '<p><img src=""/></p>'
    result = make_images_absolute(html, BASE)
    assert "<img" not in result


def test_missing_src_image_is_removed() -> None:
    """Images with no src attribute are removed entirely."""
    html = "<p><img/></p>"
    result = make_images_absolute(html, BASE)
    assert "<img" not in result


def test_mixed_images_keeps_only_valid() -> None:
    """Valid and invalid images in the same HTML: only valid ones are kept."""
    html = '<p><img src="/a.png"/><img src="data:image/png;base64,xyz"/><img src="https://other.com/b.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/a.png"' in result
    assert 'src="https://other.com/b.png"' in result
    assert "data:" not in result


def test_no_images_is_noop() -> None:
    """HTML with no images is returned unchanged (modulo parser normalisation)."""
    html = "<p>just text</p>"
    result = make_images_absolute(html, BASE)
    assert "just text" in result
    assert "<img" not in result


# ---------------------------------------------------------------------------
# preprocess_figures tests
# ---------------------------------------------------------------------------


def test_preprocess_figures_converts_text_figure_to_blockquote() -> None:
    """A figure containing text paragraphs is converted to a blockquote."""
    html = "<figure><div><p>This is a quote</p></div></figure>"
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None
    assert soup.find("figure") is None
    assert "This is a quote" in result


def test_preprocess_figures_image_only_figure_unchanged() -> None:
    """A figure containing only an image is NOT converted to a blockquote."""
    html = '<figure><img src="https://example.com/img.png" alt="test"/></figure>'
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None
    assert soup.find("blockquote") is None


def test_preprocess_figures_image_with_figcaption_only_unchanged() -> None:
    """A figure with only an image and figcaption is not converted."""
    html = '<figure><img src="https://example.com/img.png"/><figcaption>Caption</figcaption></figure>'
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None
    assert soup.find("blockquote") is None


def test_preprocess_figures_figcaption_moved_after_blockquote() -> None:
    """The figcaption is placed after the blockquote, not inside it."""
    html = (
        "<figure><div><p>Quote text</p></div><figcaption><a href='https://example.com'>Author</a></figcaption></figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    blockquote = soup.find("blockquote")
    figcaption = soup.find("figcaption")
    assert blockquote is not None
    assert figcaption is not None
    # figcaption should not be inside blockquote
    assert figcaption.find_parent("blockquote") is None
    assert blockquote.find("figcaption") is None
    # figcaption text is still present
    assert "Author" in result


def test_preprocess_figures_no_figures_is_noop() -> None:
    """HTML without any <figure> elements is returned unchanged."""
    html = "<p>Just a paragraph</p>"
    result = preprocess_figures(html)
    assert "Just a paragraph" in result
    assert "<figure" not in result
    assert "<blockquote" not in result


def test_preprocess_figures_github_quote_example() -> None:
    """Real-world GitHub quote figure is correctly converted to a blockquote."""
    html = (
        '<figure class="not-prose">'
        '<a href="https://github.com/example" rel="noopener noreferrer">'
        "<svg></svg>"
        "</a>"
        '<div class="gh-quote-body">'
        "<p>I have done everything you asked.</p>"
        "</div>"
        "<figcaption>"
        '<img src="https://avatars.githubusercontent.com/user?size=32" alt="user" width="24"/>'
        '<a href="https://github.com/example">@user · Feb 13, 2021</a>'
        "</figcaption>"
        "</figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None
    assert soup.find("figure") is None
    assert "I have done everything you asked." in result
    assert "@user" in result


def test_preprocess_figures_preserves_quote_text_content() -> None:
    """All text content within the figure body is preserved in the blockquote."""
    html = "<figure><p>First sentence.</p><p>Second sentence.</p></figure>"
    result = preprocess_figures(html)
    assert "First sentence." in result
    assert "Second sentence." in result
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None


# ---------------------------------------------------------------------------
# message_map tests
# ---------------------------------------------------------------------------

_ARTICLE_LINKS = {
    "telegraph_link": "https://telegra.ph/test-article",
    "article_link": "https://example.com/article",
    "discussion_link": "https://lobste.rs/s/abc123",
    "title": "Test Article",
}


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


# ---------------------------------------------------------------------------
# _extract_reaction_row tests
# ---------------------------------------------------------------------------

_MSG_MAP: dict[str, dict[str, str]] = {
    "123:456": _ARTICLE_LINKS,
}


def test_extract_reaction_row_empty_new_reaction() -> None:
    """Returns a removal row when new_reaction is empty (reaction removed)."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "user": {"id": 789, "username": "alice"},
        "new_reaction": [],
        "old_reaction": [{"type": "emoji", "emoji": "👍"}],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["emojis"] == ""
    assert row["user_id"] == "789"


def test_extract_reaction_row_non_emoji_reaction() -> None:
    """Returns a removal row when the reaction changes to custom-only content."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "user": {"id": 789, "username": "alice"},
        "new_reaction": [{"type": "custom_emoji", "custom_emoji_id": "12345"}],
        "old_reaction": [],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["emojis"] == ""


def test_extract_reaction_row_unknown_message() -> None:
    """Returns None when the message_id is not in the message map."""
    reaction = {
        "chat": {"id": 999},
        "message_id": 1,
        "user": {"id": 789, "username": "alice"},
        "new_reaction": [{"type": "emoji", "emoji": "👍"}],
        "old_reaction": [],
    }
    assert _extract_reaction_row(reaction, _MSG_MAP) is None


def test_extract_reaction_row_known_message_with_username() -> None:
    """Returns a complete row when the message is tracked and user has a username."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "user": {"id": 789, "username": "alice"},
        "new_reaction": [{"type": "emoji", "emoji": "👍"}],
        "old_reaction": [],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["username"] == "alice"
    assert row["user_id"] == "789"
    assert row["emojis"] == "👍"
    assert row["telegraph_link"] == _ARTICLE_LINKS["telegraph_link"]
    assert row["article_link"] == _ARTICLE_LINKS["article_link"]
    assert row["discussion_link"] == _ARTICLE_LINKS["discussion_link"]
    assert "reacted_at" in row


def test_extract_reaction_row_fallback_to_first_name() -> None:
    """Falls back to first_name when username is absent."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "user": {"id": 789, "first_name": "Bob"},
        "new_reaction": [{"type": "emoji", "emoji": "❤️"}],
        "old_reaction": [],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["username"] == "Bob"


def test_extract_reaction_row_multiple_emojis() -> None:
    """Multiple emoji reactions are joined with a space."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "user": {"id": 789, "username": "carol"},
        "new_reaction": [
            {"type": "emoji", "emoji": "👍"},
            {"type": "emoji", "emoji": "🔥"},
        ],
        "old_reaction": [],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["emojis"] == "👍 🔥"


def test_extract_reaction_row_actor_chat_fallback() -> None:
    """Uses actor_chat when user is absent (e.g. anonymous group reaction)."""
    reaction = {
        "chat": {"id": 123},
        "message_id": 456,
        "actor_chat": {"id": 555, "title": "My Channel"},
        "new_reaction": [{"type": "emoji", "emoji": "🎉"}],
        "old_reaction": [],
    }
    row = _extract_reaction_row(reaction, _MSG_MAP)
    assert row is not None
    assert row["username"] == "My Channel"
    assert row["user_id"] == "555"


def test_apply_runtime_config_updates_new_state_paths() -> None:
    """apply_runtime_config updates message-map and bookmark paths along with others."""
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
