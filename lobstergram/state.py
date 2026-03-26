"""Persistent state: processed items, subscribers, message map, bookmarks."""

from __future__ import annotations

from lobstergram import config
from lobstergram.db import get_connection, init_db


def _ensure_db() -> None:
    init_db()


# ---------------------------------------------------------------------------
# Seen items (processed RSS entries)
# ---------------------------------------------------------------------------


_SEEN_ITEMS_MAX_SIZE = 5000


def load_state() -> dict[str, object]:
    _ensure_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM seen_items").fetchall()
    return {"seen": [row[0] for row in rows]}


def save_state(state: dict[str, object]) -> None:
    _ensure_db()
    seen_ids: list[str] = list(state.get("seen", []))
    # Cap size to most recent entries.
    if len(seen_ids) > _SEEN_ITEMS_MAX_SIZE:
        seen_ids = seen_ids[-_SEEN_ITEMS_MAX_SIZE:]
    with get_connection() as conn:
        conn.execute("DELETE FROM seen_items")
        conn.executemany("INSERT INTO seen_items (id) VALUES (?)", [(i,) for i in seen_ids])


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------


def load_subscribers() -> dict[str, object]:
    _ensure_db()
    with get_connection() as conn:
        sub_rows = conn.execute(
            "SELECT chat_id, type, username, first_name, last_name FROM subscribers"
        ).fetchall()
        meta_row = conn.execute(
            "SELECT value FROM meta WHERE key='last_update_id'"
        ).fetchone()
    subscribers = [
        {
            "chat_id": row[0],
            "type": row[1],
            "username": row[2],
            "first_name": row[3],
            "last_name": row[4],
        }
        for row in sub_rows
    ]
    last_update_id = int(meta_row[0]) if meta_row else 0
    return {"subscribers": subscribers, "last_update_id": last_update_id}


def save_subscribers(state: dict[str, object]) -> None:
    _ensure_db()
    subscribers: list[dict[str, object]] = list(state.get("subscribers", []))
    last_update_id: int = int(state.get("last_update_id", 0))
    with get_connection() as conn:
        conn.execute("DELETE FROM subscribers")
        conn.executemany(
            "INSERT INTO subscribers (chat_id, type, username, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    sub.get("chat_id"),
                    sub.get("type"),
                    sub.get("username"),
                    sub.get("first_name"),
                    sub.get("last_name"),
                )
                for sub in subscribers
            ],
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_update_id', ?)",
            (str(last_update_id),),
        )


# ---------------------------------------------------------------------------
# Message map
# ---------------------------------------------------------------------------


def load_message_map() -> dict[str, dict[str, str]]:
    _ensure_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, telegraph_link, article_link, discussion_link, title FROM message_map"
        ).fetchall()
    return {
        row[0]: {
            "telegraph_link": row[1] or "",
            "article_link": row[2] or "",
            "discussion_link": row[3] or "",
            "title": row[4] or "",
        }
        for row in rows
    }


def save_message_map(msg_map: dict[str, dict[str, str]]) -> None:
    _ensure_db()
    # Cap to most recent entries (dict preserves insertion order in Python 3.7+).
    if len(msg_map) > config._MESSAGE_MAP_MAX_SIZE:
        msg_map = dict(list(msg_map.items())[-config._MESSAGE_MAP_MAX_SIZE :])
    with get_connection() as conn:
        conn.execute("DELETE FROM message_map")
        conn.executemany(
            "INSERT INTO message_map"
            " (key, telegraph_link, article_link, discussion_link, title)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (
                    key,
                    links.get("telegraph_link", ""),
                    links.get("article_link", ""),
                    links.get("discussion_link", ""),
                    links.get("title", ""),
                )
                for key, links in msg_map.items()
            ],
        )


def update_message_map(sent: dict[str | int, int], article_links: dict[str, str]) -> None:
    """Persist chat_id:message_id → article_links so reactions can be resolved later."""
    if not sent:
        return
    _ensure_db()
    rows = [
        (
            f"{chat_id}:{message_id}",
            article_links.get("telegraph_link", ""),
            article_links.get("article_link", ""),
            article_links.get("discussion_link", ""),
            article_links.get("title", ""),
        )
        for chat_id, message_id in sent.items()
    ]
    with get_connection() as conn:
        # INSERT OR REPLACE here because we append entries incrementally (unlike
        # save_message_map which replaces the whole table at once).
        conn.executemany(
            "INSERT OR REPLACE INTO message_map"
            " (key, telegraph_link, article_link, discussion_link, title)"
            " VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    # Trim to max size.
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM message_map").fetchone()[0]
        if count > config._MESSAGE_MAP_MAX_SIZE:
            conn.execute(
                """DELETE FROM message_map WHERE key IN (
                    SELECT key FROM message_map ORDER BY inserted_at ASC LIMIT ?
                )""",
                (count - config._MESSAGE_MAP_MAX_SIZE,),
            )


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------


def load_bookmarks() -> list[dict[str, str]]:
    _ensure_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT telegraph_link, article_link, discussion_link, username, user_id, emojis, reacted_at FROM bookmarks"
        ).fetchall()
    return [
        {
            "telegraph_link": row[0] or "",
            "article_link": row[1] or "",
            "discussion_link": row[2] or "",
            "username": row[3] or "",
            "user_id": row[4] or "",
            "emojis": row[5] or "",
            "reacted_at": row[6] or "",
        }
        for row in rows
    ]


def save_bookmarks(rows: list[dict[str, str]]) -> None:
    _ensure_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM bookmarks")
        conn.executemany(
            "INSERT INTO bookmarks"
            " (telegraph_link, article_link, discussion_link, username, user_id, emojis, reacted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row.get("telegraph_link", ""),
                    row.get("article_link", ""),
                    row.get("discussion_link", ""),
                    row.get("username", ""),
                    row.get("user_id", ""),
                    row.get("emojis", ""),
                    row.get("reacted_at", ""),
                )
                for row in rows
            ],
        )


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
    """Apply reaction updates so bookmarks table reflects the current state."""
    if not updates:
        return 0
    existing_rows = load_bookmarks()
    synced_rows, changed = sync_bookmark_rows(existing_rows, updates)
    if not changed:
        return 0
    save_bookmarks(synced_rows)
    config.log("info", f"bookmarks synced updates={len(updates)} rows={len(synced_rows)}")
    return len(updates)

