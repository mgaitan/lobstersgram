"""Persistent state: processed items, subscribers, message map, bookmarks."""

from __future__ import annotations

import csv
import json

from lobstergram import config


def load_state() -> dict[str, object]:
    if not config.STATE_PATH.exists():
        return {"seen": []}
    return json.loads(config.STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, object]) -> None:
    config.STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_subscribers() -> dict[str, object]:
    if not config.SUBSCRIBERS_PATH.exists():
        return {"subscribers": [], "last_update_id": 0}
    return json.loads(config.SUBSCRIBERS_PATH.read_text(encoding="utf-8"))


def save_subscribers(state: dict[str, object]) -> None:
    config.SUBSCRIBERS_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_message_map() -> dict[str, dict[str, str]]:
    if not config.MESSAGE_MAP_PATH.exists():
        return {}
    return json.loads(config.MESSAGE_MAP_PATH.read_text(encoding="utf-8"))


def save_message_map(msg_map: dict[str, dict[str, str]]) -> None:
    # Cap to most recent entries (dict preserves insertion order in Python 3.7+).
    if len(msg_map) > config._MESSAGE_MAP_MAX_SIZE:
        msg_map = dict(list(msg_map.items())[-config._MESSAGE_MAP_MAX_SIZE :])
    config.MESSAGE_MAP_PATH.write_text(json.dumps(msg_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_message_map(sent: dict[str | int, int], article_links: dict[str, str]) -> None:
    """Persist chat_id:message_id → article_links so reactions can be resolved later."""
    if not sent:
        return
    msg_map = load_message_map()
    for chat_id, message_id in sent.items():
        key = f"{chat_id}:{message_id}"
        msg_map[key] = article_links
    save_message_map(msg_map)


def load_bookmarks() -> list[dict[str, str]]:
    if not config.BOOKMARKS_PATH.exists() or config.BOOKMARKS_PATH.stat().st_size == 0:
        return []
    with config.BOOKMARKS_PATH.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def save_bookmarks(rows: list[dict[str, str]]) -> None:
    with config.BOOKMARKS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=config.BOOKMARK_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _get_bookmark_key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("user_id", ""), row.get("article_link", "")


def sync_bookmark_rows(
    existing_rows: list[dict[str, str]],
    updates: list[dict[str, str]],
) -> tuple[list[dict[str, str]], bool]:
    rows = list(existing_rows)
    changed = False
    for update in updates:
        identity = _get_bookmark_key(update)
        filtered_rows = [row for row in rows if _get_bookmark_key(row) != identity]
        if len(filtered_rows) != len(rows):
            changed = True
        rows = filtered_rows
        if update.get("emojis"):
            changed = True
            rows.append(update)
    return rows, changed


def sync_bookmarks(updates: list[dict[str, str]]) -> int:
    """Apply reaction updates so bookmark.csv reflects the current state."""
    if not updates:
        return 0
    existing_rows = load_bookmarks()
    synced_rows, changed = sync_bookmark_rows(existing_rows, updates)
    if not changed:
        return 0
    save_bookmarks(synced_rows)
    config.log("info", f"bookmarks synced updates={len(updates)} rows={len(synced_rows)}")
    return len(updates)
