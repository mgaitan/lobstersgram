"""Application services shared by HTTP routes and bookmarklets."""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

from markdown_this import add_front_matter, extract_main_content, markdown_to_text, split_front_matter
from md_to_telegraph import create_account, create_page

from markdown_web.schemas import SourceMetadata, SourceRequest

DEFAULT_ACCOUNT_NAME = "markdown-web"
DEFAULT_AUTHOR_NAME = "markdown-web"


class SourceError(ValueError):
    """Raised when a request does not contain a usable source."""


class MissingSourceError(SourceError):
    """Raised when a request contains no URL, HTML, or Markdown."""

    def __init__(self) -> None:
        super().__init__("Provide one of url, html, or markdown")


class UnknownBookmarkletError(SourceError):
    """Raised when a bookmarklet key is not known by this process."""

    def __init__(self) -> None:
        super().__init__("Unknown or expired bookmarklet key")


class InvalidURLSourceError(SourceError):
    """Raised when a URL source is not an HTTP(S) URL."""

    def __init__(self) -> None:
        super().__init__("URL sources must use http or https")


@dataclass(frozen=True)
class PreparedContent:
    """Normalized content ready for Markdown output or Telegraph."""

    title: str
    markdown: str
    fallback_text: str
    metadata: SourceMetadata


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


class BookmarkletTokenStore:
    """Keep short-lived bookmarklet keys separate from raw Telegraph tokens."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._lock = threading.Lock()

    def create(self, token: str) -> str:
        key = secrets.token_urlsafe(24)
        with self._lock:
            self._tokens[key] = token
        return key

    def resolve(self, key: str | None) -> str | None:
        if not key:
            return None
        with self._lock:
            return self._tokens.get(key)


telegraph_tokens = TelegraphTokenStore()
bookmarklet_tokens = BookmarkletTokenStore()


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


def publish_content(request: SourceRequest, bookmarklet_key: str | None = None) -> str:
    """Publish request content to Telegraph and return its public URL."""
    prepared = prepare_content(request)
    token = request.access_token or bookmarklet_tokens.resolve(bookmarklet_key)
    token = telegraph_tokens.resolve(token)
    return create_page(
        title=prepared.title or None,
        content_markdown=prepared.markdown,
        fallback_text=prepared.fallback_text,
        access_token=token,
    )


def require_bookmarklet_token(key: str | None) -> str:
    """Return a token for a bookmarklet request or raise a useful source error."""
    if not (token := bookmarklet_tokens.resolve(key)):
        raise UnknownBookmarkletError
    return token
