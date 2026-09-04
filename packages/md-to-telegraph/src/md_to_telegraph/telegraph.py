"""Telegraph API client for Markdown content."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

from md_to_telegraph.markdown import extract_leading_title, strip_leading_title_heading
from md_to_telegraph.md_to_dom import content_to_telegraph, prepend_image
from md_to_telegraph.metadata import split_front_matter

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 20
HTTP_SERVER_ERROR_MIN = 500
NON_DOCUMENT_TYPES = frozenset(
    {
        "category",
        "categorypage",
        "collection",
        "collectionpage",
        "home",
        "homepage",
        "itemlist",
        "landingpage",
        "profilepage",
        "search",
        "searchpage",
        "searchresultspage",
        "section",
        "sectionpage",
        "website",
    }
)
TELEGRAPH_CREATE_PAGE_URL = "https://api.telegra.ph/createPage"
TELEGRAPH_EDIT_PAGE_URL = "https://api.telegra.ph/editPage"
TELEGRAPH_CREATE_ACCOUNT_URL = "https://api.telegra.ph/createAccount"
TELEGRAPH_PAGE_MAX_CHARS = 40_000
MARKDOWN_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class TelegraphPages:
    """Telegraph URLs and Markdown chunks created for one publication."""

    urls: tuple[str, ...]
    markdowns: tuple[str, ...]


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


class TelegraphContentError(RuntimeError):
    """Raised when metadata identifies a source as a non-document page."""

    def __init__(self, page_type: str) -> None:
        super().__init__(f"Refusing to publish non-document page (type: {page_type})")


def _is_non_document_type(page_type: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", page_type.casefold())
    return normalized in NON_DOCUMENT_TYPES


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
        try:
            data = response.json()
        except ValueError:
            logger.warning("Telegraph returned a non-JSON response attempt=%s/%s", attempt, attempts)
            data = {"ok": False, "error": "invalid_json_response"}
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


def _page_payload(  # noqa: PLR0913
    title: str | None = None,
    content_markdown: Path | str = "",
    fallback_text: str = "",
    source_url: str = "",
    author_name: str = "",
    access_token: str | None = None,
) -> dict[str, object]:
    """Build the common API payload for creating or editing a page."""
    token = access_token or os.getenv("TELEGRAPH_API_TOKEN")
    if not token:
        raise TelegraphTokenError

    markdown = content_markdown.read_text(encoding="utf-8") if isinstance(content_markdown, Path) else content_markdown
    metadata, markdown = split_front_matter(markdown)
    if (page_type := metadata.get("type", "")) and _is_non_document_type(page_type):
        raise TelegraphContentError(page_type)
    resolved_title = title or metadata.get("title") or extract_leading_title(markdown)
    if not resolved_title and isinstance(content_markdown, Path):
        resolved_title = content_markdown.stem
    if not resolved_title:
        raise TelegraphTitleError

    page_title = resolved_title[:256]
    markdown = strip_leading_title_heading(markdown, page_title)
    source_url = source_url or metadata.get("url", "")
    author_name = author_name or metadata.get("author", "") or _source_domain(source_url)
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
    return payload


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
    payload = _page_payload(
        title=title,
        content_markdown=content_markdown,
        fallback_text=fallback_text,
        source_url=source_url,
        author_name=author_name,
        access_token=access_token,
    )

    logger.debug("Create Telegraph page title=%r url=%s", str(payload["title"])[:80], source_url)
    data = _post_with_retry(TELEGRAPH_CREATE_PAGE_URL, payload, request_timeout, retry_attempts)
    telegraph_url = str(data["result"]["url"])
    if warm_cache:
        warm_telegraph_cache(telegraph_url, request_timeout)
    return telegraph_url


def edit_page(  # noqa: PLR0913
    path: str,
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
    """Replace a Telegraph page's content and return its public URL."""
    payload = _page_payload(
        title=title,
        content_markdown=content_markdown,
        fallback_text=fallback_text,
        source_url=source_url,
        author_name=author_name,
        access_token=access_token,
    )
    payload["path"] = path

    logger.debug("Edit Telegraph page path=%s title=%r", path, str(payload["title"])[:80])
    data = _post_with_retry(TELEGRAPH_EDIT_PAGE_URL, payload, request_timeout, retry_attempts)
    telegraph_url = str(data["result"]["url"])
    if warm_cache:
        warm_telegraph_cache(telegraph_url, request_timeout)
    return telegraph_url


def _markdown_blocks(body: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    fence_char = ""
    fence_length = 0
    for line in body.splitlines():
        if fence_char:
            current.append(line)
            if re.match(rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$", line):
                fence_char = ""
            continue
        if match := MARKDOWN_FENCE_RE.match(line):
            fence_char = match.group(1)[0]
            fence_length = len(match.group(1))
            current.append(line)
        elif line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current).strip())
            current = []
    if current:
        blocks.append("\n".join(current).strip())
    return blocks


def split_markdown_pages(markdown: str, max_chars: int = TELEGRAPH_PAGE_MAX_CHARS) -> list[str]:
    """Split Markdown between blocks without cutting a paragraph or Markdown construct."""
    _metadata, body = split_front_matter(markdown.strip())
    blocks = _markdown_blocks(body)
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in blocks:
        block_size = len(block) + (2 if current else 0)
        if current and current_size + block_size > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0
        current.append(block)
        current_size += len(block) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [body.strip()]


def page_navigation(urls: tuple[str, ...], index: int) -> str:
    """Return previous/next links for one page in a Telegraph page set."""
    links: list[str] = []
    if index:
        links.append(f"[Página anterior]({urls[index - 1]})")
    if index + 1 < len(urls):
        links.append(f"[Página siguiente]({urls[index + 1]})")
    return "\n\n---\n\n" + " | ".join(links) if links else ""


def _prepend_metadata(markdown: str, metadata: dict[str, str]) -> str:
    if not metadata:
        return markdown
    front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{front_matter}\n---\n\n{markdown}"


def create_pages(  # noqa: PLR0913
    title: str | None = None,
    content_markdown: Path | str = "",
    fallback_text: str = "",
    source_url: str = "",
    author_name: str = "",
    access_token: str | None = None,
    *,
    max_chars: int = TELEGRAPH_PAGE_MAX_CHARS,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    retry_attempts: int | None = None,
    warm_cache: bool = True,
) -> TelegraphPages:
    """Create one or more linked Telegraph pages for Markdown content."""
    markdown = content_markdown.read_text(encoding="utf-8") if isinstance(content_markdown, Path) else content_markdown
    metadata, body = split_front_matter(markdown.strip())
    chunks = split_markdown_pages(markdown, max_chars=max_chars)
    if len(chunks) == 1:
        url = create_page(
            title=title,
            content_markdown=markdown,
            fallback_text=fallback_text,
            source_url=source_url,
            author_name=author_name,
            access_token=access_token,
            request_timeout=request_timeout,
            retry_attempts=retry_attempts,
            warm_cache=warm_cache,
        )
        return TelegraphPages((url,), (markdown,))

    page_markdowns = tuple(_prepend_metadata(chunk, metadata) for chunk in chunks)
    base_title = title or metadata.get("title") or extract_leading_title(body) or "Document"
    urls = tuple(
        create_page(
            title=base_title if index == 0 else f"{base_title} ({index + 1}/{len(chunks)})",
            content_markdown=page_markdown,
            fallback_text=fallback_text if index == 0 else "",
            source_url=source_url,
            author_name=author_name,
            access_token=access_token,
            request_timeout=request_timeout,
            retry_attempts=retry_attempts,
            warm_cache=False,
        )
        for index, (chunk, page_markdown) in enumerate(zip(chunks, page_markdowns, strict=True))
    )
    for index, (url, page_markdown) in enumerate(zip(urls, page_markdowns, strict=True)):
        edit_page(
            path=urlparse(url).path.lstrip("/"),
            title=base_title if index == 0 else f"{base_title} ({index + 1}/{len(chunks)})",
            content_markdown=page_markdown + page_navigation(urls, index),
            fallback_text=fallback_text if index == 0 else "",
            source_url=source_url,
            author_name=author_name,
            access_token=access_token,
            request_timeout=request_timeout,
            retry_attempts=retry_attempts,
            warm_cache=warm_cache,
        )
    return TelegraphPages(urls, page_markdowns)


def _source_domain(source_url: str) -> str:
    """Return a readable default author name for a source URL."""
    hostname = urlparse(source_url).hostname or ""
    return hostname.removeprefix("www.")
