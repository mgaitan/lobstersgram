"""Pipeline orchestration: feed processing and message formatting."""

from __future__ import annotations

import html
import time
import urllib.parse

import feedparser

from lobstergram import config
from lobstergram.content import collect_new_items, extract_main_content, fetch_url
from lobstergram.models import Item
from lobstergram.state import load_state, load_subscribers, save_state, update_message_map
from lobstergram.telegram import resolve_recipient_chat_ids, send_to_recipients
from lobstergram.telegraph import telegraph_create_page


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
    discussion_html = f'🦞 <a href="{html.escape(discussion_link)}">Lobsters thread</a>' if discussion_link else ""

    return (
        f"<b>{title}</b>\n"
        f"<i>{src}</i>\n"
        f"{tags_html}"
        f"{intro_html}\n\n"
        f'📖 <a href="{turl}">Read on telegra.ph</a>\n'
        f'🌐 <a href="{ourl}">Original</a>\n'
        f"{discussion_html}"
    )


def build_recipients() -> list[str | int]:
    subscribers_state = load_subscribers()
    subscribers = subscribers_state.get("subscribers") or []
    recipients = resolve_recipient_chat_ids(subscribers)
    if not recipients:
        config.log("warn", "no subscribers configured")
    return recipients


def build_item_message(item: Item) -> tuple[str, dict[str, str]]:
    final_url = fetch_url(item.link)
    extracted_title, content_markdown, fallback_text, intro = extract_main_content(final_url)
    telegraph_title = extracted_title if extracted_title and extracted_title != final_url else item.title
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
    article_links = {
        "telegraph_link": telegraph_url,
        "article_link": final_url,
        "discussion_link": item.discussion_link,
        "title": item.title,
    }
    return msg, article_links


def handle_single_url(url: str) -> int:
    item = Item(
        id=url,
        title=url,
        link=url,
        discussion_link="",
        source=urllib.parse.urlparse(url).netloc or "direct",
        tags=[],
    )
    msg, article_links = build_item_message(item)
    recipients = build_recipients()
    sent = send_to_recipients(recipients, msg, disable_preview=True)
    update_message_map(sent, article_links)
    print("Processed single URL.")
    return 0


def process_feed() -> int:
    state = load_state()
    seen: set[str] = set(state.get("seen", []))

    feed = feedparser.parse(config.RSS_URL)
    entries = getattr(feed, "entries", []) or []
    config.log("info", f"feed entries={len(entries)}")

    new_items = collect_new_items(entries, seen)

    # Process oldest->newest for nicer ordering
    new_items.reverse()
    new_items = new_items[: config.MAX_ITEMS_PER_RUN]

    if not new_items:
        print("No new items.")
        return 0

    recipients = build_recipients()

    for item in new_items:
        try:
            config.log("info", f"process item title={item.title!r} link={item.link}")
            msg, article_links = build_item_message(item)
            sent = send_to_recipients(recipients, msg, disable_preview=True)
            update_message_map(sent, article_links)

            seen.add(item.id)
            # Be gentle with API limits
            time.sleep(1.2)

        except Exception as exc:  # noqa: BLE001
            # Don't fail the whole run on one bad link; log silently instead of
            # notifying subscribers with a noisy "Failed to process" message.
            config.log(
                "error",
                f"process failed title={item.title!r} err={type(exc).__name__}: {exc}",
            )
            seen.add(item.id)  # avoid retry loops

    state["seen"] = list(seen)[-5000:]  # cap size
    save_state(state)
    print(f"Processed {len(new_items)} items.")
    return 0
