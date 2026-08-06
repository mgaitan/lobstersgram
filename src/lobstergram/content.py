"""Lobsters feed content models and link normalization."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    link: str
    discussion_link: str
    source: str
    tags: list[str]


def is_lobsters_discussion(url: str) -> bool:
    """Return whether *url* points to a Lobsters discussion."""
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.endswith("lobste.rs") and parsed.path.startswith("/s/")


def normalize_id(entry: object) -> str:
    """Get a stable feed entry identifier, falling back to its link or title."""
    for key in ("id", "guid", "link"):
        value = getattr(entry, key, None)
        if value:
            return str(value)
    return str(hash(getattr(entry, "title", "")))


def collect_new_items(entries: list[object], seen: set[str]) -> list[Item]:
    """Convert unseen feed entries into application items."""
    new_items: list[Item] = []
    for entry in entries:
        item_id = normalize_id(entry)
        if item_id in seen:
            continue

        link = getattr(entry, "link", "") or ""
        discussion_link = getattr(entry, "comments", "") or ""
        if not discussion_link and is_lobsters_discussion(link):
            discussion_link = link
        if is_lobsters_discussion(link):
            links = getattr(entry, "links", []) or []
            for link_info in links:
                href = link_info.get("href") or ""
                if href and not is_lobsters_discussion(href):
                    link = href
                    break
        title = getattr(entry, "title", link) or link
        source = urllib.parse.urlparse(link).netloc or "lobste.rs"
        tags = [tag.get("term", "") for tag in getattr(entry, "tags", []) or []]
        tags = [tag for tag in tags if tag]
        new_items.append(
            Item(
                id=item_id,
                title=title,
                link=link,
                discussion_link=discussion_link,
                source=source,
                tags=tags,
            )
        )
    return new_items
