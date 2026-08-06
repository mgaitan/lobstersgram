"""Tests for Telegram API helpers."""

from __future__ import annotations

import os

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstersgram.telegram import _extract_reaction_row

_ARTICLE_LINKS = {
    "telegraph_link": "https://telegra.ph/test-article",
    "article_link": "https://example.com/article",
    "discussion_link": "https://lobste.rs/s/abc123",
    "title": "Test Article",
}

_MSG_MAP: dict[str, dict[str, str]] = {
    "123:456": _ARTICLE_LINKS,
}

# ---------------------------------------------------------------------------
# _extract_reaction_row tests
# ---------------------------------------------------------------------------


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
