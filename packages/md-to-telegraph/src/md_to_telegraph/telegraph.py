"""Telegraph API client for Markdown content."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

from md_to_telegraph.markdown import extract_leading_title, strip_leading_title_heading
from md_to_telegraph.md_to_dom import content_to_telegraph, prepend_image
from md_to_telegraph.metadata import split_front_matter

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 20
HTTP_SERVER_ERROR_MIN = 500
TELEGRAPH_CREATE_PAGE_URL = "https://api.telegra.ph/createPage"
TELEGRAPH_CREATE_ACCOUNT_URL = "https://api.telegra.ph/createAccount"


class TelegraphAPIError(RuntimeError):
    """Raised when Telegraph returns an unsuccessful API response."""

    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegraph API error")
        self.data = data


class TelegraphTokenError(RuntimeError):
    """Raised when a page needs an access token but none was provided."""

    def __init__(self) -> None:
        super().__init__("Pass access_token or set TELEGRAPH_API_TOKEN before creating a page")


class TelegraphTitleError(RuntimeError):
    """Raised when a page has no explicit or discoverable title."""

    def __init__(self) -> None:
        super().__init__("Pass title or include a title in YAML front matter or the first Markdown heading")


def _post_with_retry(
    endpoint: str,
    payload: dict[str, object],
    request_timeout: int,
    retry_attempts: int | None,
) -> dict[str, object]:
    """POST a Telegraph API method, retrying transient responses when requested."""
    attempts = max(1, retry_attempts or 1)
    for attempt in range(1, attempts + 1):
        backoff = min(2.0**attempt, 30.0)
        response = requests.post(endpoint, data=payload, timeout=request_timeout)
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
        return data
    msg = "Telegraph request exhausted all attempts without raising"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


def create_account(
    short_name: str,
    author_name: str = "",
    author_url: str = "",
    *,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    retry_attempts: int | None = None,
) -> str:
    """Create a Telegraph account and return its access token."""
    payload: dict[str, object] = {"short_name": short_name}
    if author_name:
        payload["author_name"] = author_name
    if author_url:
        payload["author_url"] = author_url
    data = _post_with_retry(TELEGRAPH_CREATE_ACCOUNT_URL, payload, request_timeout, retry_attempts)
    result = data.get("result")
    if not isinstance(result, dict) or not result.get("access_token"):
        raise TelegraphAPIError(data)
    return str(result["access_token"])


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
    title: str | None = None,
    content_markdown: Path | str = "",
    fallback_text: str = "",
    source_url: str = "",
    author_name: str = "",
    access_token: str | None = None,
    *,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    retry_attempts: int | None = None,
    warm_cache: bool = True,
) -> str:
    """Create a Telegraph page from Markdown and return its URL.

    ``retry_attempts=None`` performs one request. Set it to a larger value to
    retry transient server responses and unsuccessful Telegraph API responses.
    """
    token = access_token or os.getenv("TELEGRAPH_API_TOKEN")
    if not token:
        raise TelegraphTokenError

    markdown = content_markdown.read_text(encoding="utf-8") if isinstance(content_markdown, Path) else content_markdown
    metadata, markdown = split_front_matter(markdown)
    resolved_title = title or metadata.get("title") or extract_leading_title(markdown)
    if not resolved_title and isinstance(content_markdown, Path):
        resolved_title = content_markdown.stem
    if not resolved_title:
        raise TelegraphTitleError

    page_title = resolved_title[:256]
    markdown = strip_leading_title_heading(markdown, page_title)
    source_url = source_url or metadata.get("url", "")
    author_name = author_name or metadata.get("author", "")
    nodes = prepend_image(content_to_telegraph(markdown, fallback_text), metadata.get("image", ""))
    payload: dict[str, object] = {
        "access_token": token,
        "title": page_title,
        "content": json.dumps(nodes, ensure_ascii=False),
        "return_content": False,
    }
    if author_name:
        payload["author_name"] = author_name
    if source_url:
        payload["author_url"] = source_url

    logger.debug("Create Telegraph page title=%r url=%s", page_title[:80], source_url)
    data = _post_with_retry(TELEGRAPH_CREATE_PAGE_URL, payload, request_timeout, retry_attempts)
    telegraph_url = str(data["result"]["url"])
    if warm_cache:
        warm_telegraph_cache(telegraph_url, request_timeout)
    return telegraph_url
