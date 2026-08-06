"""Runtime configuration, constants, and logging helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAPH_ACCESS_TOKEN = os.environ["TELEGRAPH_ACCESS_TOKEN"]
TELEGRAM_DEV_CHAT_ID = os.getenv("TELEGRAM_DEV_CHAT_ID")

STATE_PATH = Path("state.json")
MESSAGE_MAP_PATH = Path(os.getenv("MESSAGE_MAP_PATH", "message_map.json"))
BOOKMARKS_PATH = Path(os.getenv("BOOKMARKS_PATH", "bookmark.csv"))
RSS_URL = "https://lobste.rs/rss"
MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "5"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
SUBSCRIBERS_PATH = Path(os.getenv("SUBSCRIBERS_PATH", "subscribers.json"))
TELEGRAM_RETRY_ATTEMPTS = max(1, int(os.getenv("TELEGRAM_RETRY_ATTEMPTS", "3")))
TELEGRAPH_RETRY_ATTEMPTS = max(1, int(os.getenv("TELEGRAPH_RETRY_ATTEMPTS", "3")))
INTER_MESSAGE_DELAY = max(0.0, float(os.getenv("INTER_MESSAGE_DELAY", "0.5")))

_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_FORBIDDEN = 403
_HTTP_SERVER_ERROR_MIN = 500
INTRO_MIN_LENGTH = 40
MIN_CONTENT_LENGTH = 200
_MESSAGE_MAP_MAX_SIZE = 10000
BOOKMARK_FIELDNAMES = [
    "telegraph_link",
    "article_link",
    "discussion_link",
    "username",
    "user_id",
    "emojis",
    "reacted_at",
]

console = Console()


def level_enabled(level: str) -> bool:
    order = {"debug": 10, "info": 20, "warn": 30, "error": 40}
    return order.get(level, 20) >= order.get(LOG_LEVEL, 20)


def log(level: str, message: str) -> None:
    if level_enabled(level):
        console.log(f"[{level}] {message}")
