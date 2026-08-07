"""Application services shared by HTTP routes and bookmarklets."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from markdown_this import add_front_matter, extract_main_content, markdown_to_text, split_front_matter
from md_to_telegraph import create_account, create_page

from markdown_web.schemas import SourceMetadata, SourceRequest

DEFAULT_ACCOUNT_NAME = "page-to-telegraph"
DEFAULT_AUTHOR_NAME = "page-to-telegraph"
TELEGRAPH_API_URL = "https://api.telegra.ph"
TELEGRAPH_PAGE_LIST_LIMIT = 200
TELEGRAPH_REQUEST_TIMEOUT = 20


class SourceError(ValueError):
    """Raised when a request does not contain a usable source."""


class MissingSourceError(SourceError):
    """Raised when a request contains no URL, HTML, or Markdown."""

    def __init__(self) -> None:
        super().__init__("Provide one of url, html, or markdown")


class InvalidURLSourceError(SourceError):
    """Raised when a URL source is not an HTTP(S) URL."""

    def __init__(self) -> None:
        super().__init__("URL sources must use http or https")


class TelegraphAPIError(RuntimeError):
    """Raised when Telegraph cannot return a valid API response."""

    def __init__(self) -> None:
        super().__init__("Could not read the Telegraph page list")


@dataclass(frozen=True)
class PreparedContent:
    """Normalized content ready for Markdown output or Telegraph."""

    title: str
    markdown: str
    fallback_text: str
    metadata: SourceMetadata


def list_published_pages() -> tuple[int, list[dict[str, object]]]:
    """Return all pages published by the configured Telegraph account."""
    token = telegraph_tokens.resolve()
    pages: list[dict[str, object]] = []
    offset = 0
    total_count = 0

    while True:
        try:
            response = requests.get(
                f"{TELEGRAPH_API_URL}/getPageList",
                params={
                    "access_token": token,
                    "offset": offset,
                    "limit": TELEGRAPH_PAGE_LIST_LIMIT,
                },
                timeout=TELEGRAPH_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelegraphAPIError from exc

        if not isinstance(payload, dict) or not payload.get("ok"):
            raise TelegraphAPIError
        result = payload.get("result")
        if not isinstance(result, dict):
            raise TelegraphAPIError

        raw_total = result.get("total_count", 0)
        raw_pages = result.get("pages", [])
        if not isinstance(raw_total, int) or not isinstance(raw_pages, list):
            raise TelegraphAPIError
        total_count = raw_total
        pages.extend(page for page in raw_pages if isinstance(page, dict))

        if not raw_pages or len(pages) >= total_count:
            return total_count, pages
        offset += len(raw_pages)


class TelegraphTokenStore:
    """Resolve tokens without putting Telegraph bearer tokens in bookmarklets."""

    def __init__(self) -> None:
        self._token = ""
        self._lock = threading.Lock()

    def resolve(self, explicit_token: str | None = None) -> str:
        if explicit_token:
            return explicit_token
        if environment_token := os.getenv("TELEGRAPH_API_TOKEN"):
            return environment_token
        if self._token:
            return self._token

        with self._lock:
            if not self._token:
                self._token = create_account(
                    short_name=os.getenv("TELEGRAPH_ACCOUNT_SHORT_NAME", DEFAULT_ACCOUNT_NAME)[:32],
                    author_name=os.getenv("TELEGRAPH_ACCOUNT_AUTHOR", DEFAULT_AUTHOR_NAME),
                    author_url=os.getenv("TELEGRAPH_ACCOUNT_AUTHOR_URL", ""),
                )
        return self._token


telegraph_tokens = TelegraphTokenStore()
published_urls: dict[str, str] = {}
published_urls_lock = threading.Lock()


def _require_source(request: SourceRequest) -> str:
    if request.url:
        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidURLSourceError
        return request.url
    if request.html is not None:
        return request.html
    if request.markdown is not None:
        return request.markdown
    raise MissingSourceError


def _merge_metadata(markdown: str, supplied: SourceMetadata) -> tuple[str, SourceMetadata]:
    existing, body = split_front_matter(markdown.strip())
    merged = {**existing, **supplied.values()}
    return add_front_matter(body, merged), SourceMetadata.model_validate(merged)


def prepare_content(request: SourceRequest) -> PreparedContent:
    """Extract and normalize a request into Markdown with YAML front matter."""
    source = _require_source(request)
    if request.url:
        title, markdown, fallback_text, _intro = extract_main_content(request.url)
    elif request.html is not None:
        title, markdown, fallback_text, _intro = extract_main_content(request.html)
    else:
        front_matter, body = split_front_matter(source.strip())
        title = front_matter.get("title", "")
        markdown = source
        fallback_text = markdown_to_text(body)

    markdown, metadata = _merge_metadata(markdown, request.metadata)
    title = metadata.title or title
    return PreparedContent(title=title, markdown=markdown, fallback_text=fallback_text, metadata=metadata)


def _publish_content(request: SourceRequest) -> str:
    """Publish request content to Telegraph and return its public URL."""
    prepared = prepare_content(request)
    token = request.access_token
    token = telegraph_tokens.resolve(token)
    return create_page(
        title=prepared.title or None,
        content_markdown=prepared.markdown,
        fallback_text=prepared.fallback_text,
        source_url=prepared.metadata.url,
        author_name=prepared.metadata.author,
        access_token=token,
    )


def publish_content(
    request: SourceRequest,
    cache_key: str | None = None,
) -> str:
    """Publish content, optionally reusing the Telegraph page for a source URL."""
    if not cache_key:
        return _publish_content(request)

    with published_urls_lock:
        if target := published_urls.get(cache_key):
            return target
        target = _publish_content(request)
        published_urls[cache_key] = target
        return target
