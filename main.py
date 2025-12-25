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
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markdownify import markdownify as html_to_md
from readability import Document
from rich.console import Console

from md_to_dom import md_to_dom

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAPH_ACCESS_TOKEN = os.environ["TELEGRAPH_ACCESS_TOKEN"]
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_PATH = Path("state.json")
RSS_URL = "https://lobste.rs/rss"
MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "5"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
SUBSCRIBERS_PATH = Path(os.getenv("SUBSCRIBERS_PATH", "subscribers.json"))

console = Console()


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    link: str
    discussion_link: str
    source: str
    tags: list[str]


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


def load_subscribers() -> dict[str, Any]:
    if not SUBSCRIBERS_PATH.exists():
        return {"subscribers": [], "last_update_id": 0}
    return json.loads(SUBSCRIBERS_PATH.read_text(encoding="utf-8"))


def save_subscribers(state: dict[str, Any]) -> None:
    SUBSCRIBERS_PATH.write_text(
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


def telegram_get_updates(offset: int) -> list[dict[str, Any]]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 0, "offset": offset}
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram getUpdates failed: {data!r}")
    return data.get("result", [])


def read_new_subscribers() -> int:
    state = load_subscribers()
    last_update_id = int(state.get("last_update_id") or 0)
    offset = last_update_id + 1 if last_update_id else 0
    updates = telegram_get_updates(offset)
    if not updates:
        log("info", "read_messages no updates")
        return 0

    subscribers = {s.get("chat_id"): s for s in state.get("subscribers", [])}
    max_update_id = last_update_id
    new_count = 0
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        if update_id > max_update_id:
            max_update_id = update_id
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        if not text.startswith("/start"):
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not chat_id:
            continue
        if chat_id in subscribers:
            continue
        subscribers[chat_id] = {
            "chat_id": chat_id,
            "type": chat.get("type"),
            "username": chat.get("username"),
            "first_name": chat.get("first_name"),
            "last_name": chat.get("last_name"),
        }
        new_count += 1

    state["subscribers"] = list(subscribers.values())
    state["last_update_id"] = max_update_id
    save_subscribers(state)
    log("info", f"read_messages new_subscribers={new_count}")
    return new_count


def is_lobsters_discussion(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.endswith("lobste.rs") and parsed.path.startswith("/s/")


def extract_intro(markdown_text: str, fallback_text: str) -> str:
    text = markdown_to_text(markdown_text)
    for chunk in text.split("\n\n"):
        line = chunk.strip()
        if not line:
            continue
        intro = line.replace("\n", " ").strip()
        if len(intro) >= 40:
            return intro
    # Fallback: first non-empty line from text
    for line in fallback_text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def markdown_to_text(markdown_text: str) -> str:
    text = markdown_text
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"[_*]{1,3}([^_*]+)[_*]{1,3}", r"\1", text)
    return text


def extract_main_content(url: str) -> tuple[str, str, str, str]:
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
    intro = extract_intro(extracted_markdown, fallback_text)
    return title, extracted_markdown, fallback_text, intro


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


def telegram_send_message(
    chat_id: str | int, text_html: str, disable_preview: bool = False
) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    log("debug", f"telegram_send_message preview_disabled={disable_preview}")
    r = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()


def format_message(
    item: Item,
    telegraph_url: str,
    original_url: str,
    intro: str,
) -> str:
    title = html.escape(item.title)
    src = html.escape(item.source)
    turl = html.escape(telegraph_url)
    ourl = html.escape(original_url)
    tags = ", ".join(item.tags) if item.tags else ""
    tags_html = f"\n<i>Tags:</i> {html.escape(tags)}" if tags else ""
    intro_html = f"\n\n{html.escape(intro)}" if intro else ""
    discussion_link = item.discussion_link.strip()
    discussion_html = (
        f'🦞 <a href="{html.escape(discussion_link)}">Lobsters thread</a>'
        if discussion_link
        else ""
    )

    return (
        f"<b>{title}</b>\n"
        f"<i>{src}</i>\n"
        f"{tags_html}"
        f"{intro_html}\n\n"
        f'📖 <a href="{turl}">Read on telegra.ph</a>\n'
        f'🌐 <a href="{ourl}">Original</a>\n'
        f"{discussion_html}"
    )


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
    parser.add_argument("--rss-url", default=RSS_URL)
    parser.add_argument("--state-path", default=str(STATE_PATH))
    parser.add_argument("--subscribers-path", default=str(SUBSCRIBERS_PATH))
    parser.add_argument("--max-items", type=int, default=MAX_ITEMS_PER_RUN)
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT)
    parser.add_argument("--log-level", default=LOG_LEVEL)
    return parser.parse_args()


def main() -> int:
    global RSS_URL, STATE_PATH, MAX_ITEMS_PER_RUN, REQUEST_TIMEOUT, LOG_LEVEL
    global SUBSCRIBERS_PATH
    args = parse_args()
    RSS_URL = args.rss_url
    STATE_PATH = Path(args.state_path)
    SUBSCRIBERS_PATH = Path(args.subscribers_path)
    MAX_ITEMS_PER_RUN = args.max_items
    REQUEST_TIMEOUT = args.timeout
    LOG_LEVEL = args.log_level.lower()

    log(
        "info",
        f"start rss={RSS_URL} state={STATE_PATH} max_items={MAX_ITEMS_PER_RUN} timeout={REQUEST_TIMEOUT} log_level={LOG_LEVEL}",
    )

    if args.read_messages:
        read_new_subscribers()
        print("Read messages.")
        return 0

    if args.url:
        item = Item(
            id=args.url,
            title=args.url,
            link=args.url,
            discussion_link="",
            source=urllib.parse.urlparse(args.url).netloc or "direct",
            tags=[],
        )
        try:
            final_url = fetch_url(item.link)
            (
                extracted_title,
                content_markdown,
                fallback_text,
                intro,
            ) = extract_main_content(final_url)
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
                item,
                telegraph_url=telegraph_url,
                original_url=final_url,
                intro=intro,
            )
            subscribers_state = load_subscribers()
            subscribers = subscribers_state.get("subscribers", [])
            if subscribers:
                for sub in subscribers:
                    telegram_send_message(sub["chat_id"], msg, disable_preview=True)
            elif TELEGRAM_CHAT_ID:
                telegram_send_message(TELEGRAM_CHAT_ID, msg, disable_preview=True)
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
        discussion_link = getattr(e, "comments", "") or ""
        if not discussion_link and is_lobsters_discussion(link):
            discussion_link = link
        if is_lobsters_discussion(link):
            links = getattr(e, "links", []) or []
            for l in links:
                href = l.get("href") or ""
                if href and not is_lobsters_discussion(href):
                    link = href
                    break
        title = getattr(e, "title", link) or link
        source = urllib.parse.urlparse(link).netloc or "lobste.rs"
        tags = [t.get("term", "") for t in getattr(e, "tags", []) or []]
        tags = [t for t in tags if t]
        new_items.append(
            Item(
                id=iid,
                title=title,
                link=link,
                discussion_link=discussion_link,
                source=source,
                tags=tags,
            )
        )

    # Process oldest->newest for nicer ordering
    new_items.reverse()
    new_items = new_items[:MAX_ITEMS_PER_RUN]

    if not new_items:
        print("No new items.")
        return 0

    subscribers_state = load_subscribers()
    subscribers = subscribers_state.get("subscribers", [])
    if not subscribers and not TELEGRAM_CHAT_ID:
        log("warn", "no subscribers configured")

    for item in new_items:
        try:
            log("info", f"process item title={item.title!r} link={item.link}")
            final_url = fetch_url(item.link)
            (
                extracted_title,
                content_markdown,
                fallback_text,
                intro,
            ) = extract_main_content(final_url)

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
                item,
                telegraph_url=telegraph_url,
                original_url=final_url,
                intro=intro,
            )
            if subscribers:
                for sub in subscribers:
                    telegram_send_message(sub["chat_id"], msg, disable_preview=True)
            elif TELEGRAM_CHAT_ID:
                telegram_send_message(TELEGRAM_CHAT_ID, msg, disable_preview=True)

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
            error_msg = (
                f"<b>⚠️ Failed to process:</b> {html.escape(item.title)}\n"
                f"<code>{err}</code>\n{html.escape(item.link)}"
            )
            if subscribers:
                for sub in subscribers:
                    telegram_send_message(
                        sub["chat_id"], error_msg, disable_preview=True
                    )
            elif TELEGRAM_CHAT_ID:
                telegram_send_message(TELEGRAM_CHAT_ID, error_msg, disable_preview=True)
            seen.add(item.id)  # avoid retry loops; remove if you prefer retries

    state["seen"] = list(seen)[-5000:]  # cap size
    save_state(state)
    print(f"Processed {len(new_items)} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
