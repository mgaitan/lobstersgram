#!/usr/bin/env python3
"""
Lobsters -> Telegraph -> Telegram (serverless via GitHub Actions).

- Polls Lobsters RSS
- Extracts full article content (trafilatura)
- Publishes to telegra.ph
- Sends a Telegram message with the Telegraph link
- Deduplicates via state.json committed back to the repo
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markdownify import markdownify as html_to_md
from readability import Document
from rich.console import Console

from md_to_dom import md_to_dom

load_dotenv()

STATE_PATH = Path("state.json")
RSS_URL = "https://lobste.rs/rss"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAPH_ACCESS_TOKEN = os.environ["TELEGRAPH_ACCESS_TOKEN"]

MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "5"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()

console = Console()


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    link: str
    source: str


def level_enabled(level: str) -> bool:
    order = {"debug": 10, "info": 20, "warn": 30, "error": 40}
    return order.get(level, 20) >= order.get(LOG_LEVEL, 20)


def log(level: str, message: str) -> None:
    if level_enabled(level):
        console.log(f"[{level}] {message}")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"seen": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def normalize_id(entry: Any) -> str:
    # Prefer feed-provided id/guid; fallback to link.
    for key in ("id", "guid", "link"):
        v = getattr(entry, key, None)
        if v:
            return str(v)
    return str(hash(getattr(entry, "title", "")))


def fetch_url(url: str) -> str:
    # Follow redirects to final URL.
    log("debug", f"fetch_url start url={url}")
    r = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )
    r.raise_for_status()
    log("debug", f"fetch_url final url={r.url} status={r.status_code}")
    return r.url


def fetch_html(url: str) -> Optional[str]:
    r = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "lobsters-telegraph-bot"},
    )
    r.raise_for_status()
    return r.text


def extract_main_content(url: str) -> tuple[str, str, str]:
    """
    Returns (title, markdown_content, fallback_text).
    """
    downloaded = fetch_html(url)
    if not downloaded:
        raise RuntimeError("Failed to download content")

    log("debug", f"extract_main_content downloaded_len={len(downloaded)} url={url}")
    content_html = ""
    title = url
    try:
        doc = Document(downloaded)
        content_html = doc.summary() or ""
        title = doc.title() or url
        log(
            "debug",
            f"extract_main_content readability_len={len(content_html)} url={url}",
        )
    except Exception as exc:
        log("warn", f"readability failed err={type(exc).__name__}: {exc}")

    if not content_html or len(content_html.strip()) < 200:
        log("warn", f"extract_main_content content_len={len(content_html)} url={url}")
        content_html = downloaded

    extracted_markdown = html_to_md(content_html)
    log(
        "debug",
        f"extract_main_content markdown_len={len(extracted_markdown)} url={url}",
    )

    soup = BeautifulSoup(content_html, "html.parser")
    fallback_text = soup.get_text(separator="\n").strip()
    return title, extracted_markdown, fallback_text


def telegraph_create_page(
    title: str,
    content_markdown: str,
    fallback_text: str,
    source_url: str,
) -> str:
    """
    Creates a Telegraph page from HTML content.
    Telegraph expects 'content' as a JSON array of nodes.
    Easiest minimal approach: wrap the HTML as a single <p> with escaped text is bad.
    Better: use Telegraph HTML mode? Telegraph API uses node JSON, but it also accepts
    'content' as JSON string of nodes. We'll create a small set of nodes by splitting paragraphs.
    """
    # Build nodes from Markdown first; fallback to plain paragraphs.
    nodes: list[dict[str, Any]] = []
    markdown = content_markdown.strip()
    if markdown:
        nodes = md_to_dom(markdown)

    if not nodes:
        text = fallback_text.strip()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for p in paragraphs[:2000]:
            nodes.append({"tag": "p", "children": [p]})

    if not nodes:
        nodes = [{"tag": "p", "children": ["(No content extracted)"]}]

    payload = {
        "access_token": TELEGRAPH_ACCESS_TOKEN,
        "title": title[:256],
        "content": json.dumps(nodes, ensure_ascii=False),
        "return_content": False,
    }

    # Optional: include source attribution
    if source_url:
        payload["author_name"] = "Source"
        payload["author_url"] = source_url

    log("debug", f"telegraph_create_page title={title[:80]!r} url={source_url}")
    r = requests.post(
        "https://api.telegra.ph/createPage", data=payload, timeout=REQUEST_TIMEOUT
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph error: {data}")
    return data["result"]["url"]


def telegram_send_message(text_html: str, disable_preview: bool = False) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    log("debug", f"telegram_send_message preview_disabled={disable_preview}")
    r = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()


def format_message(item: Item, telegraph_url: str, original_url: str) -> str:
    title = html.escape(item.title)
    src = html.escape(item.source)
    turl = html.escape(telegraph_url)
    ourl = html.escape(original_url)

    return (
        f"<b>{title}</b>\n"
        f"<i>{src}</i>\n\n"
        f'📖 <a href="{turl}">Read on telegra.ph</a>\n'
        f'🌐 <a href="{ourl}">Original</a>\n'
        f'🦞 <a href="{html.escape(item.link)}">Lobsters thread</a>'
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lobsters -> Telegraph -> Telegram",
    )
    parser.add_argument("--url", help="Process a single URL and exit")
    parser.add_argument("--rss-url", default=RSS_URL)
    parser.add_argument("--state-path", default=str(STATE_PATH))
    parser.add_argument("--max-items", type=int, default=MAX_ITEMS_PER_RUN)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT)
    parser.add_argument("--log-level", default=LOG_LEVEL)
    return parser.parse_args()


def main() -> int:
    global RSS_URL, STATE_PATH, MAX_ITEMS_PER_RUN, REQUEST_TIMEOUT, LOG_LEVEL
    args = parse_args()
    RSS_URL = args.rss_url
    STATE_PATH = Path(args.state_path)
    MAX_ITEMS_PER_RUN = args.max_items
    REQUEST_TIMEOUT = args.timeout
    LOG_LEVEL = args.log_level.lower()

    log(
        "info",
        f"start rss={RSS_URL} state={STATE_PATH} max_items={MAX_ITEMS_PER_RUN} timeout={REQUEST_TIMEOUT} log_level={LOG_LEVEL}",
    )

    if args.url:
        item = Item(
            id=args.url,
            title=args.url,
            link=args.url,
            source=urllib.parse.urlparse(args.url).netloc or "direct",
        )
        try:
            final_url = fetch_url(item.link)
            extracted_title, content_markdown, fallback_text = extract_main_content(
                final_url
            )
            telegraph_title = (
                extracted_title
                if extracted_title and extracted_title != final_url
                else item.title
            )
            telegraph_url = telegraph_create_page(
                title=telegraph_title,
                content_markdown=content_markdown,
                fallback_text=fallback_text,
                source_url=final_url,
            )
            msg = format_message(
                item, telegraph_url=telegraph_url, original_url=final_url
            )
            telegram_send_message(msg, disable_preview=True)
            print("Processed single URL.")
            return 0
        except Exception as exc:
            log("error", f"single url failed err={type(exc).__name__}: {exc}")
            raise
    state = load_state()
    seen: set[str] = set(state.get("seen", []))

    feed = feedparser.parse(RSS_URL)
    entries = getattr(feed, "entries", []) or []
    log("info", f"feed entries={len(entries)}")

    new_items: list[Item] = []
    for e in entries:
        iid = normalize_id(e)
        if iid in seen:
            continue

        link = getattr(e, "link", "") or ""
        title = getattr(e, "title", link) or link
        source = urllib.parse.urlparse(link).netloc or "lobste.rs"
        new_items.append(Item(id=iid, title=title, link=link, source=source))

    # Process oldest->newest for nicer ordering
    new_items.reverse()
    new_items = new_items[:MAX_ITEMS_PER_RUN]

    if not new_items:
        print("No new items.")
        return 0

    for item in new_items:
        try:
            log("info", f"process item title={item.title!r} link={item.link}")
            final_url = fetch_url(item.link)
            extracted_title, content_markdown, fallback_text = extract_main_content(
                final_url
            )

            telegraph_title = (
                extracted_title
                if extracted_title and extracted_title != final_url
                else item.title
            )
            telegraph_url = telegraph_create_page(
                title=telegraph_title,
                content_markdown=content_markdown,
                fallback_text=fallback_text,
                source_url=final_url,
            )

            msg = format_message(
                item, telegraph_url=telegraph_url, original_url=final_url
            )
            telegram_send_message(msg, disable_preview=True)

            seen.add(item.id)
            # Be gentle with API limits
            time.sleep(1.2)

        except Exception as exc:
            # Don't fail the whole run on one bad link.
            log(
                "error",
                f"process failed title={item.title!r} err={type(exc).__name__}: {exc}",
            )
            err = html.escape(f"{type(exc).__name__}: {exc}")
            telegram_send_message(
                f"<b>⚠️ Failed to process:</b> {html.escape(item.title)}\n<code>{err}</code>\n{html.escape(item.link)}",
                disable_preview=True,
            )
            seen.add(item.id)  # avoid retry loops; remove if you prefer retries

    state["seen"] = list(seen)[-5000:]  # cap size
    save_state(state)
    print(f"Processed {len(new_items)} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
