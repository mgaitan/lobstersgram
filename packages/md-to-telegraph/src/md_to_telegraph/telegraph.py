"""Telegraph API client for Markdown content."""

from __future__ import annotations

import json
import logging
import time

import requests

from md_to_telegraph.md_to_dom import content_to_telegraph

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 20
HTTP_SERVER_ERROR_MIN = 500
TELEGRAPH_CREATE_PAGE_URL = "https://api.telegra.ph/createPage"


class TelegraphAPIError(RuntimeError):
    """Raised when Telegraph returns an unsuccessful API response."""

    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegraph API error")
        self.data = data


def _post_with_retry(
    payload: dict[str, object],
    request_timeout: int,
    retry_attempts: int | None,
) -> str:
    """Create a Telegraph page, retrying transient responses when requested."""
    attempts = max(1, retry_attempts or 1)
    for attempt in range(1, attempts + 1):
        backoff = min(2.0**attempt, 30.0)
        response = requests.post(TELEGRAPH_CREATE_PAGE_URL, data=payload, timeout=request_timeout)
        if response.status_code >= HTTP_SERVER_ERROR_MIN:
            logger.warning("Telegraph server error status=%s attempt=%s/%s", response.status_code, attempt, attempts)
            if attempt < attempts:
                time.sleep(backoff)
                continue
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.warning("Telegraph API error attempt=%s/%s data=%s", attempt, attempts, data)
            if attempt < attempts:
                time.sleep(backoff)
                continue
            raise TelegraphAPIError(data)
        return str(data["result"]["url"])
    msg = "Telegraph request exhausted all attempts without raising"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


def warm_telegraph_cache(url: str, request_timeout: int = DEFAULT_REQUEST_TIMEOUT) -> None:
    """Fetch a Telegraph page once to prime its Instant View cache."""
    try:
        logger.debug("Warm Telegraph cache url=%s", url)
        response = requests.get(url, timeout=request_timeout, headers={"User-Agent": "md-to-telegraph"})
        response.raise_for_status()
        logger.info("Warmed Telegraph cache status=%s url=%s", response.status_code, url)
    except requests.RequestException as exc:
        logger.warning("Failed to warm Telegraph cache error=%s", exc)


def create_page(  # noqa: PLR0913
    access_token: str,
    title: str,
    content_markdown: str,
    fallback_text: str = "",
    source_url: str = "",
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    retry_attempts: int | None = None,
    warm_cache: bool = True,
) -> str:
    """Create a Telegraph page from Markdown and return its URL.

    ``retry_attempts=None`` performs one request. Set it to a larger value to
    retry transient server responses and unsuccessful Telegraph API responses.
    """
    nodes = content_to_telegraph(content_markdown, fallback_text)
    payload: dict[str, object] = {
        "access_token": access_token,
        "title": title[:256],
        "content": json.dumps(nodes, ensure_ascii=False),
        "return_content": False,
    }
    if source_url:
        payload["author_name"] = "Source"
        payload["author_url"] = source_url

    logger.debug("Create Telegraph page title=%r url=%s", title[:80], source_url)
    telegraph_url = _post_with_retry(payload, request_timeout, retry_attempts)
    if warm_cache:
        warm_telegraph_cache(telegraph_url, request_timeout)
    return telegraph_url
