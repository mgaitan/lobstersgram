"""Application services shared by HTTP routes and bookmarklets."""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, replace
from urllib.parse import urlparse

import requests
from markdown_this import add_front_matter, extract_main_content, markdown_to_text, split_front_matter
from md_to_telegraph import create_account, create_page, edit_page

from markdown_web.schemas import SourceMetadata, SourceRequest

DEFAULT_ACCOUNT_NAME = "page-to-telegraph"
DEFAULT_AUTHOR_NAME = "page-to-telegraph"
TELEGRAPH_API_URL = "https://api.telegra.ph"
TELEGRAPH_PAGE_LIST_LIMIT = 200
TELEGRAPH_REQUEST_TIMEOUT = 20
CARD_DIRECTIVE_RE = re.compile(r"!\[card\]\(\s*(https?://[^)\s]+)\s*\)")


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


class SourceHTTPError(SourceError):
    """Raised when a source responds with an HTTP error."""

    def __init__(self, status: int) -> None:
        if status in {401, 403}:
            message = f"Source denied server access (HTTP {status}). Send the page HTML through /bookmarklet/ instead."
        else:
            message = f"Source returned HTTP {status}"
        super().__init__(message)


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
    intro: str = ""


@dataclass(frozen=True)
class PublishedBriefArticle:
    """An extracted article and the Telegraph page created for this brief."""

    source_url: str
    content: PreparedContent
    telegraph_url: str


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
        try:
            title, markdown, fallback_text, intro = extract_main_content(request.url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            raise SourceHTTPError(status) from exc
    elif request.html is not None:
        title, markdown, fallback_text, intro = extract_main_content(request.html)
    else:
        front_matter, body = split_front_matter(source.strip())
        title = front_matter.get("title", "")
        markdown = source
        fallback_text = markdown_to_text(body)
        intro = ""

    markdown, metadata = _merge_metadata(markdown, request.metadata)
    title = metadata.title or title
    return PreparedContent(
        title=title,
        markdown=markdown,
        fallback_text=fallback_text,
        metadata=metadata,
        intro=intro,
    )


def _publish_prepared(prepared: PreparedContent, token: str, *, warm_cache: bool = True) -> str:
    return create_page(
        title=prepared.title or None,
        content_markdown=prepared.markdown,
        fallback_text=prepared.fallback_text,
        source_url=prepared.metadata.url,
        author_name=prepared.metadata.author,
        access_token=token,
        warm_cache=warm_cache,
    )


def _publish_content(request: SourceRequest) -> str:
    """Publish request content to Telegraph and return its public URL."""
    prepared = prepare_content(request)
    token = telegraph_tokens.resolve(request.access_token)
    return _publish_prepared(prepared, token)


def _escape_markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _card_markdown(article: PublishedBriefArticle) -> str:
    title = _escape_markdown_text(article.content.title or article.source_url)
    parts = ["---"]
    if image_url := article.content.metadata.image:
        parts.append(f"[![{title}]({image_url})]({article.telegraph_url})")
    parts.append(f"**[{title}]({article.telegraph_url})**")
    if article.content.intro:
        parts.append(article.content.intro)
    parts.append(f"[Leer en Telegraph]({article.telegraph_url})")
    parts.append("---")
    return "\n\n".join(parts)


def _navigation_markdown(
    brief_url: str,
    previous_url: str | None,
    next_url: str | None,
) -> str:
    links: list[str] = []
    if previous_url:
        links.append(f"[Artículo anterior]({previous_url})")
    links.append(f"[Volver al boletín]({brief_url})")
    if next_url:
        links.append(f"[Artículo siguiente]({next_url})")
    return "\n\n---\n\n" + " | ".join(links)


def card_source_urls(markdown: str) -> list[str]:
    """Return unique card source URLs in their first-seen order."""
    return list(dict.fromkeys(CARD_DIRECTIVE_RE.findall(markdown)))


def publish_brief_article(source_url: str, token: str, *, warm_cache: bool = True) -> PublishedBriefArticle:
    """Extract and publish one article referenced by a brief."""
    content = prepare_content(SourceRequest(url=source_url))
    return PublishedBriefArticle(
        source_url=source_url,
        content=content,
        telegraph_url=_publish_prepared(content, token, warm_cache=warm_cache),
    )


def publish_brief_page(
    brief: PreparedContent,
    articles: list[PublishedBriefArticle],
    token: str,
    *,
    warm_cache: bool = True,
) -> str:
    """Expand article cards and publish the parent brief."""
    articles_by_source = {article.source_url: article for article in articles}
    expanded_markdown = CARD_DIRECTIVE_RE.sub(
        lambda match: _card_markdown(articles_by_source[match.group(1)]),
        brief.markdown,
    )
    return _publish_prepared(replace(brief, markdown=expanded_markdown), token, warm_cache=warm_cache)


def add_brief_navigation(  # noqa: PLR0913
    article: PublishedBriefArticle,
    index: int,
    articles: list[PublishedBriefArticle],
    brief_url: str,
    token: str,
    *,
    warm_cache: bool = True,
) -> str:
    """Add parent, previous, and next links to one published article."""
    previous_url = articles[index - 1].telegraph_url if index else None
    next_url = articles[index + 1].telegraph_url if index + 1 < len(articles) else None
    return edit_page(
        path=urlparse(article.telegraph_url).path.lstrip("/"),
        title=article.content.title or None,
        content_markdown=(article.content.markdown + _navigation_markdown(brief_url, previous_url, next_url)),
        fallback_text=article.content.fallback_text,
        source_url=article.content.metadata.url or article.source_url,
        author_name=article.content.metadata.author,
        access_token=token,
        warm_cache=warm_cache,
    )


def _publish_brief(request: SourceRequest) -> str:
    brief = prepare_content(request)
    token = telegraph_tokens.resolve(request.access_token)
    articles = [publish_brief_article(source_url, token) for source_url in card_source_urls(brief.markdown)]
    brief_url = publish_brief_page(brief, articles, token)

    for index, article in enumerate(articles):
        add_brief_navigation(article, index, articles, brief_url, token)
    return brief_url


def publish_content(
    request: SourceRequest,
    cache_key: str | None = None,
) -> str:
    """Publish content, optionally reusing the Telegraph page for a source URL."""
    if request.markdown and CARD_DIRECTIVE_RE.search(request.markdown):
        return _publish_brief(request)
    if not cache_key:
        return _publish_content(request)

    with published_urls_lock:
        if target := published_urls.get(cache_key):
            return target
        target = _publish_content(request)
        published_urls[cache_key] = target
        return target
