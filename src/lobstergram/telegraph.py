"""Telegraph API interactions."""

from __future__ import annotations

import json
import time

import requests
from markdown_this import strip_leading_title_heading
from md_to_telegraph import md_to_telegraph

from lobstergram import config


class TelegraphAPIError(RuntimeError):
    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegraph API error")
        self.data = data


def _telegraph_post_with_retry(payload: dict[str, object]) -> str:
    """POST to Telegraph createPage API with retry on transient errors.

    Returns the created page URL on success, raises on permanent failure.
    """
    for attempt in range(1, config.TELEGRAPH_RETRY_ATTEMPTS + 1):
        backoff = min(2.0**attempt, 30.0)
        r = requests.post("https://api.telegra.ph/createPage", data=payload, timeout=config.REQUEST_TIMEOUT)
        if r.status_code >= config._HTTP_SERVER_ERROR_MIN:
            config.log(
                "warn",
                f"telegraph server error status={r.status_code} attempt={attempt}/{config.TELEGRAPH_RETRY_ATTEMPTS}",
            )
            if attempt < config.TELEGRAPH_RETRY_ATTEMPTS:
                time.sleep(backoff)
                continue
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            config.log(
                "warn",
                f"telegraph api error attempt={attempt}/{config.TELEGRAPH_RETRY_ATTEMPTS} data={data}",
            )
            if attempt < config.TELEGRAPH_RETRY_ATTEMPTS:
                time.sleep(backoff)
                continue
            raise TelegraphAPIError(data)
        return str(data["result"]["url"])
    msg = "telegraph_post_with_retry exhausted all attempts without raising"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


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
    nodes: list[dict[str, object]] = []
    markdown = strip_leading_title_heading(content_markdown.strip(), title)
    if markdown:
        nodes = md_to_telegraph(markdown)

    if not nodes:
        text = fallback_text.strip()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for p in paragraphs[:2000]:
            nodes.append({"tag": "p", "children": [p]})

    if not nodes:
        nodes = [{"tag": "p", "children": ["(No content extracted)"]}]

    payload: dict[str, object] = {
        "access_token": config.TELEGRAPH_ACCESS_TOKEN,
        "title": title[:256],
        "content": json.dumps(nodes, ensure_ascii=False),
        "return_content": False,
    }

    # Optional: include source attribution
    if source_url:
        payload["author_name"] = "Source"
        payload["author_url"] = source_url

    config.log("debug", f"telegraph_create_page title={title[:80]!r} url={source_url}")
    telegraph_url = _telegraph_post_with_retry(payload)
    warm_telegraph_cache(telegraph_url)
    return telegraph_url


def warm_telegraph_cache(url: str) -> None:
    """Fetch the Telegraph page once to prime the Instant View cache.

    Telegraph's Instant View requires the page to have been loaded at least
    once before Telegram will serve the cached version.  We send a plain GET
    request right after creation so the very first click from a subscriber
    already gets Instant View.
    """
    try:
        config.log("debug", f"warm_telegraph_cache url={url}")
        r = requests.get(url, timeout=config.REQUEST_TIMEOUT, headers={"User-Agent": "lobsters-telegraph-bot"})
        r.raise_for_status()
        config.log("info", f"warm_telegraph_cache ok status={r.status_code} url={url}")
    except requests.RequestException as exc:
        config.log("warn", f"warm_telegraph_cache failed err={type(exc).__name__}: {exc}")
