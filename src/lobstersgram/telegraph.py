"""Telegraph API interactions."""

from __future__ import annotations

import json
import time

import requests
from md_to_telegraph import content_to_telegraph

from lobstersgram import config


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
    """Create a Telegraph page from Markdown content and its plain-text fallback."""
    nodes = content_to_telegraph(content_markdown, fallback_text)

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
