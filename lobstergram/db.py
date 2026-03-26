"""SQLite database initialisation and connection management."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from lobstergram import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_items (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id    INTEGER PRIMARY KEY,
    type       TEXT,
    username   TEXT,
    first_name TEXT,
    last_name  TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS message_map (
    key             TEXT PRIMARY KEY,
    telegraph_link  TEXT,
    article_link    TEXT,
    discussion_link TEXT,
    title           TEXT,
    inserted_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS bookmarks (
    user_id         TEXT,
    article_link    TEXT,
    telegraph_link  TEXT,
    discussion_link TEXT,
    username        TEXT,
    emojis          TEXT,
    reacted_at      TEXT,
    PRIMARY KEY (user_id, article_link)
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a connection to the configured SQLite database, creating it if needed."""
    db_path: Path = config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create tables if they do not exist and run any pending data migrations."""
    with get_connection() as conn:
        conn.executescript(_SCHEMA)
        migrated = conn.execute("SELECT value FROM meta WHERE key='migration_done'").fetchone()
    if not migrated:
        _maybe_migrate()
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('migration_done', '1')")


# ---------------------------------------------------------------------------
# Migration helpers (one-time import of legacy flat files)
# ---------------------------------------------------------------------------


def _maybe_migrate() -> None:
    """Import legacy JSON/CSV data into SQLite if the files still exist."""
    _migrate_state()
    _migrate_subscribers()
    _migrate_message_map()
    _migrate_bookmarks()


def _migrate_state() -> None:
    legacy = Path("state.json")
    if not legacy.exists():
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        seen_ids = data.get("seen", [])
        if not seen_ids:
            return
        with get_connection() as conn:
            existing = {row[0] for row in conn.execute("SELECT id FROM seen_items")}
            new_ids = [(item_id,) for item_id in seen_ids if item_id not in existing]
            if new_ids:
                conn.executemany("INSERT OR IGNORE INTO seen_items (id) VALUES (?)", new_ids)
                config.log("info", f"migrated seen_items count={len(new_ids)} from state.json")
    except Exception as exc:  # noqa: BLE001
        config.log("warn", f"state.json migration skipped err={exc}")


def _migrate_subscribers() -> None:
    legacy = Path("subscribers.json")
    if not legacy.exists():
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        subscribers = data.get("subscribers", [])
        last_update_id = data.get("last_update_id", 0)
        with get_connection() as conn:
            for sub in subscribers:
                conn.execute(
                    """INSERT OR IGNORE INTO subscribers
                       (chat_id, type, username, first_name, last_name)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        sub.get("chat_id"),
                        sub.get("type"),
                        sub.get("username"),
                        sub.get("first_name"),
                        sub.get("last_name"),
                    ),
                )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_update_id', ?)",
                (str(last_update_id),),
            )
        if subscribers:
            config.log("info", f"migrated subscribers count={len(subscribers)} from subscribers.json")
    except Exception as exc:  # noqa: BLE001
        config.log("warn", f"subscribers.json migration skipped err={exc}")


def _migrate_message_map() -> None:
    legacy = Path("message_map.json")
    if not legacy.exists():
        return
    try:
        msg_map = json.loads(legacy.read_text(encoding="utf-8"))
        if not msg_map:
            return
        rows = [
            (
                key,
                links.get("telegraph_link", ""),
                links.get("article_link", ""),
                links.get("discussion_link", ""),
                links.get("title", ""),
            )
            for key, links in msg_map.items()
        ]
        with get_connection() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO message_map
                   (key, telegraph_link, article_link, discussion_link, title)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
        config.log("info", f"migrated message_map count={len(rows)} from message_map.json")
    except Exception as exc:  # noqa: BLE001
        config.log("warn", f"message_map.json migration skipped err={exc}")


def _migrate_bookmarks() -> None:
    legacy = Path("bookmark.csv")
    if not legacy.exists() or legacy.stat().st_size == 0:
        return
    try:
        with legacy.open(newline="", encoding="utf-8") as f:
            rows = [dict(row) for row in csv.DictReader(f)]
        if not rows:
            return
        with get_connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO bookmarks
                   (user_id, article_link, telegraph_link, discussion_link, username, emojis, reacted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        r.get("user_id", ""),
                        r.get("article_link", ""),
                        r.get("telegraph_link", ""),
                        r.get("discussion_link", ""),
                        r.get("username", ""),
                        r.get("emojis", ""),
                        r.get("reacted_at", ""),
                    )
                    for r in rows
                ],
            )
        config.log("info", f"migrated bookmarks count={len(rows)} from bookmark.csv")
    except Exception as exc:  # noqa: BLE001
        config.log("warn", f"bookmark.csv migration skipped err={exc}")
