"""Command-line interface: argument parsing and entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from lobstergram import config
from lobstergram.pipeline import handle_single_url, process_feed
from lobstergram.telegram import read_new_subscribers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lobsters -> Telegraph -> Telegram",
    )
    parser.add_argument("--url", help="Process a single URL and exit")
    parser.add_argument(
        "--read-messages",
        action="store_true",
        help="Read Telegram updates and register /start subscribers",
    )
    parser.add_argument("--rss-url", default=config.RSS_URL)
    parser.add_argument("--state-path", default=str(config.STATE_PATH))
    parser.add_argument("--message-map-path", default=str(config.MESSAGE_MAP_PATH))
    parser.add_argument("--bookmarks-path", default=str(config.BOOKMARKS_PATH))
    parser.add_argument("--subscribers-path", default=str(config.SUBSCRIBERS_PATH))
    parser.add_argument("--max-items", type=int, default=config.MAX_ITEMS_PER_RUN)
    parser.add_argument("--timeout", type=int, default=config.REQUEST_TIMEOUT)
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    parser.add_argument("--telegram-retry-attempts", type=int, default=config.TELEGRAM_RETRY_ATTEMPTS)
    parser.add_argument("--telegraph-retry-attempts", type=int, default=config.TELEGRAPH_RETRY_ATTEMPTS)
    parser.add_argument("--inter-message-delay", type=float, default=config.INTER_MESSAGE_DELAY)
    return parser.parse_args()


def apply_runtime_config(args: argparse.Namespace) -> None:
    config.RSS_URL = args.rss_url
    config.STATE_PATH = Path(args.state_path)
    config.MESSAGE_MAP_PATH = Path(args.message_map_path)
    config.BOOKMARKS_PATH = Path(args.bookmarks_path)
    config.SUBSCRIBERS_PATH = Path(args.subscribers_path)
    config.MAX_ITEMS_PER_RUN = args.max_items
    config.REQUEST_TIMEOUT = args.timeout
    config.LOG_LEVEL = args.log_level.lower()
    config.TELEGRAM_RETRY_ATTEMPTS = args.telegram_retry_attempts
    config.TELEGRAPH_RETRY_ATTEMPTS = args.telegraph_retry_attempts
    config.INTER_MESSAGE_DELAY = args.inter_message_delay


def main() -> int:
    args = parse_args()
    apply_runtime_config(args)

    config.log(
        "info",
        "start "
        f"rss={config.RSS_URL} state={config.STATE_PATH} max_items={config.MAX_ITEMS_PER_RUN} "
        f"timeout={config.REQUEST_TIMEOUT} log_level={config.LOG_LEVEL}",
    )

    if args.read_messages:
        read_new_subscribers()
        print("Read messages.")
        return 0

    if args.url:
        try:
            return handle_single_url(args.url)
        except Exception as exc:
            config.log("error", f"single url failed err={type(exc).__name__}: {exc}")
            raise

    return process_feed()
