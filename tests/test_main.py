"""Tests for main.py — blocked-subscriber auto-removal."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BLOCKED_CHAT_ID = 999
_ACTIVE_CHAT_ID = 100
_SECOND_ACTIVE_ID = 111
_THIRD_ACTIVE_ID = 222


def _make_http_error(status_code: int) -> requests.HTTPError:
    """Return an HTTPError whose response carries *status_code*."""
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code
    return requests.HTTPError(response=response)


def _subscribers_json(subscribers: list[dict[str, object]]) -> str:
    return json.dumps({"subscribers": subscribers, "last_update_id": 0})


# ---------------------------------------------------------------------------
# send_to_recipients
# ---------------------------------------------------------------------------


def test_send_to_recipients_returns_empty_on_success() -> None:
    """When all sends succeed, send_to_recipients returns an empty list."""
    with patch("main.telegram_send_message") as mock_send:
        mock_send.return_value = None
        result = main.send_to_recipients([_SECOND_ACTIVE_ID, _THIRD_ACTIVE_ID], "hello")
    assert result == []
    assert mock_send.call_count == 2  # noqa: PLR2004


def test_send_to_recipients_returns_blocked_chat_id_on_403() -> None:
    """A 403 response marks the chat_id as blocked and is returned."""
    with patch("main.telegram_send_message") as mock_send:
        mock_send.side_effect = _make_http_error(403)
        result = main.send_to_recipients([_SECOND_ACTIVE_ID, _THIRD_ACTIVE_ID], "hello")
    assert result == [_SECOND_ACTIVE_ID, _THIRD_ACTIVE_ID]


def test_send_to_recipients_non_403_not_in_blocked_list() -> None:
    """Non-403 HTTP errors are logged but the chat_id is NOT returned as blocked."""
    with patch("main.telegram_send_message") as mock_send:
        mock_send.side_effect = _make_http_error(500)
        result = main.send_to_recipients([_SECOND_ACTIVE_ID], "hello")
    assert result == []


def test_send_to_recipients_mixed_blocked_and_success() -> None:
    """Only chat_ids that returned 403 appear in the blocked list."""

    def side_effect(chat_id: int, *_: object, **__: object) -> None:
        if chat_id == _BLOCKED_CHAT_ID:
            raise _make_http_error(403)

    with patch("main.telegram_send_message", side_effect=side_effect):
        result = main.send_to_recipients([_SECOND_ACTIVE_ID, _BLOCKED_CHAT_ID, _THIRD_ACTIVE_ID], "hello")
    assert result == [_BLOCKED_CHAT_ID]


def test_send_to_recipients_inter_message_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTER_MESSAGE_DELAY is respected between sends."""
    monkeypatch.setattr(main, "INTER_MESSAGE_DELAY", 0.0)
    sleeps: list[float] = []
    with (
        patch("main.telegram_send_message"),
        patch("time.sleep", side_effect=sleeps.append),
    ):
        main.send_to_recipients([1, 2, 3], "msg")
    # Two sleeps for three recipients (between each pair)
    assert len(sleeps) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# remove_blocked_subscribers
# ---------------------------------------------------------------------------


def test_remove_blocked_subscribers_removes_matching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocked chat_ids are removed and the file is updated."""
    subs_file = tmp_path / "subscribers.json"
    subs_file.write_text(
        _subscribers_json(
            [
                {"chat_id": 1, "username": "alice"},
                {"chat_id": _BLOCKED_CHAT_ID, "username": "blocked_user"},
                {"chat_id": 3, "username": "bob"},
            ]
        )
    )
    monkeypatch.setattr(main, "SUBSCRIBERS_PATH", subs_file)

    main.remove_blocked_subscribers({_BLOCKED_CHAT_ID})

    remaining = json.loads(subs_file.read_text())["subscribers"]
    assert len(remaining) == 2  # noqa: PLR2004
    assert all(s["chat_id"] != _BLOCKED_CHAT_ID for s in remaining)


def test_remove_blocked_subscribers_noop_when_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling with an empty set must not modify the file."""
    subs_file = tmp_path / "subscribers.json"
    original = _subscribers_json([{"chat_id": 1, "username": "alice"}])
    subs_file.write_text(original)
    monkeypatch.setattr(main, "SUBSCRIBERS_PATH", subs_file)

    main.remove_blocked_subscribers(set())

    assert subs_file.read_text() == original


def test_remove_blocked_subscribers_all_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing every subscriber leaves an empty list."""
    subs_file = tmp_path / "subscribers.json"
    subs_file.write_text(_subscribers_json([{"chat_id": 1}, {"chat_id": 2}]))
    monkeypatch.setattr(main, "SUBSCRIBERS_PATH", subs_file)

    main.remove_blocked_subscribers({1, 2})

    remaining = json.loads(subs_file.read_text())["subscribers"]
    assert remaining == []


# ---------------------------------------------------------------------------
# process_feed — blocked subscribers are pruned after a run
# ---------------------------------------------------------------------------


def _make_entry(iid: str, title: str, link: str) -> MagicMock:
    entry = MagicMock()
    entry.id = iid
    entry.link = link
    entry.title = title
    entry.comments = ""
    entry.tags = []
    entry.links = []
    return entry


def test_process_feed_removes_blocked_subscribers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a run in which all recipients are blocked, they are removed from subscribers."""
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"seen": []}))
    subs_file = tmp_path / "subscribers.json"
    subs_file.write_text(
        _subscribers_json(
            [
                {"chat_id": _ACTIVE_CHAT_ID, "username": "active"},
                {"chat_id": _BLOCKED_CHAT_ID, "username": "blocked_bot"},
            ]
        )
    )

    monkeypatch.setattr(main, "STATE_PATH", state_file)
    monkeypatch.setattr(main, "SUBSCRIBERS_PATH", subs_file)
    monkeypatch.setattr(main, "MAX_ITEMS_PER_RUN", 1)
    monkeypatch.setattr(main, "INTER_MESSAGE_DELAY", 0.0)

    fake_feed = MagicMock()
    fake_feed.entries = [_make_entry("id1", "Test Article", "https://example.com/article")]

    def send_side_effect(chat_id: int, *_: object, **__: object) -> None:
        if chat_id == _BLOCKED_CHAT_ID:
            raise _make_http_error(403)

    with (
        patch("main.feedparser.parse", return_value=fake_feed),
        patch("main.build_item_message", return_value="<b>Test</b>"),
        patch("main.telegram_send_message", side_effect=send_side_effect),
        patch("time.sleep"),
    ):
        main.process_feed()

    remaining_ids = [s["chat_id"] for s in json.loads(subs_file.read_text())["subscribers"]]
    assert _BLOCKED_CHAT_ID not in remaining_ids
    assert _ACTIVE_CHAT_ID in remaining_ids


def test_process_feed_skips_blocked_for_subsequent_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once a subscriber is blocked mid-run, they are not tried for later items."""
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"seen": []}))
    subs_file = tmp_path / "subscribers.json"
    subs_file.write_text(_subscribers_json([{"chat_id": _BLOCKED_CHAT_ID, "username": "blocked"}]))

    monkeypatch.setattr(main, "STATE_PATH", state_file)
    monkeypatch.setattr(main, "SUBSCRIBERS_PATH", subs_file)
    monkeypatch.setattr(main, "MAX_ITEMS_PER_RUN", 3)
    monkeypatch.setattr(main, "INTER_MESSAGE_DELAY", 0.0)

    fake_feed = MagicMock()
    fake_feed.entries = [_make_entry(f"id{i}", f"Article {i}", f"https://example.com/{i}") for i in range(3)]

    call_count: list[int] = []

    def send_side_effect(chat_id: int, *_: object, **__: object) -> None:
        call_count.append(chat_id)
        raise _make_http_error(403)

    with (
        patch("main.feedparser.parse", return_value=fake_feed),
        patch("main.build_item_message", return_value="<b>msg</b>"),
        patch("main.telegram_send_message", side_effect=send_side_effect),
        patch("time.sleep"),
    ):
        main.process_feed()

    # The blocked subscriber should have been attempted exactly once (first item only)
    assert call_count.count(_BLOCKED_CHAT_ID) == 1
