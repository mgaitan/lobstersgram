"""Application services shared by HTTP routes and bookmarklets."""

from __future__ import annotations

import io
import os
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

import anydoc
import requests
import yaml
from markdown_this import add_front_matter, extract_main_content, markdown_to_text, split_front_matter
from md_to_telegraph import (
    TELEGRAPH_PAGE_MAX_CHARS,
    TelegraphPages,
    create_account,
    create_page,
    create_pages,
    edit_page,
    page_navigation,
    split_markdown_pages,
)
from pypdf import PdfReader, PdfWriter

from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.telegram import send_telegram_notifications

DEFAULT_ACCOUNT_NAME = "page-to-telegraph"
DEFAULT_AUTHOR_NAME = "page-to-telegraph"
TELEGRAPH_API_URL = "https://api.telegra.ph"
TELEGRAPH_PAGE_LIST_LIMIT = 200
TELEGRAPH_REQUEST_TIMEOUT = 20
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
DOCUMENT_EXTENSIONS = frozenset(
    {
        "doc",
        "docx",
        "docm",
        "ppt",
        "pptx",
        "pptm",
        "xls",
        "xlsx",
        "xlsm",
        "odt",
        "ods",
        "odp",
        "rtf",
        "epub",
        "csv",
        "pdf",
    }
)
CARD_DIRECTIVE_RE = re.compile(r"!\[card\]\(\s*(https?://[^)\s]+)\s*\)")
OCR_ERROR_RE = re.compile(r"pages?\s+(.+?)\s+of\s+\d+\s+need OCR", re.IGNORECASE)
OCR_ERROR_TYPES = tuple(
    error_type
    for error_type in (anydoc.UnsupportedError, getattr(anydoc, "NeedsOcrError", None))
    if error_type is not None
)


def _front_matter_notify_telegram(markdown: str) -> str:
    """Read the app-specific notification setting from Markdown front matter."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    try:
        end = lines.index("---", 1)
        loaded = yaml.safe_load("\n".join(lines[1:end])) or {}
    except (ValueError, yaml.YAMLError):
        return ""
    if not isinstance(loaded, Mapping):
        return ""
    value = loaded.get("notify_telegram")
    return str(value).strip() if value is not None and not isinstance(value, (dict, list)) else ""


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


class DocumentSourceError(SourceError):
    """Raised when a document cannot be converted to Markdown."""


class EmptyDocumentError(DocumentSourceError):
    def __init__(self) -> None:
        super().__init__("Uploaded document is empty")


class DocumentTooLargeError(DocumentSourceError):
    def __init__(self) -> None:
        super().__init__("Documents must be 50 MB or smaller")


class DocumentConversionError(DocumentSourceError):
    def __init__(self, detail: Exception) -> None:
        super().__init__(f"Could not convert document: {detail}")


class EmptyDocumentContentError(DocumentSourceError):
    def __init__(self) -> None:
        super().__init__("Document did not contain readable content")


class DocumentDownloadError(DocumentSourceError):
    def __init__(self) -> None:
        super().__init__("Could not download document")


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
    telegraph_urls: tuple[str, ...] = ()
    page_markdowns: tuple[str, ...] = ()


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


def _is_document_url(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    return suffix in DOCUMENT_EXTENSIONS


def _convert_document(data: bytes, filename: str) -> str:
    if not data:
        raise EmptyDocumentError
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentTooLargeError
    extension = Path(filename).suffix.lower().lstrip(".")
    document_format = anydoc.format_from_extension(extension) if extension else None
    try:
        markdown = anydoc.to_markdown_bytes(data, document_format)
    except (anydoc.ConvertError, OSError, ValueError) as exc:
        if document_format == "pdf" and _is_ocr_error(exc):
            return _convert_pdf_pages(data, exc)
        raise DocumentConversionError(exc) from exc
    if not markdown.strip():
        raise EmptyDocumentContentError
    return markdown


def _convert_pdf_pages(data: bytes, original_error: Exception) -> str:
    """Keep readable PDF pages when AnyDoc rejects scanned pages that need OCR."""
    try:
        reader = PdfReader(io.BytesIO(data))
        converted: list[tuple[int, str]] = []
        skipped: list[int] = []
        for page_number, page in enumerate(reader.pages, 1):
            writer = PdfWriter()
            writer.add_page(page)
            page_data = io.BytesIO()
            writer.write(page_data)
            try:
                page_markdown = anydoc.to_markdown_bytes(page_data.getvalue(), "pdf")
            except OCR_ERROR_TYPES as exc:
                if _is_ocr_error(exc):
                    skipped.append(page_number)
                    continue
                raise
            if page_markdown.strip():
                converted.append((page_number, page_markdown.strip()))
            else:
                skipped.append(page_number)
    except (anydoc.ConvertError, OSError, ValueError) as exc:
        raise DocumentConversionError(exc) from exc
    except Exception as exc:
        raise DocumentConversionError(exc) from exc

    if not converted:
        raise DocumentConversionError(original_error) from original_error

    parts = [f"<!-- Page {page_number} -->\n\n{page_markdown}" for page_number, page_markdown in converted]
    if skipped:
        pages = ", ".join(str(page_number) for page_number in skipped)
        warning = f"> **Contenido incompleto:** se omitieron las páginas {pages} porque requieren OCR."
        parts.insert(0, warning)
    return "\n\n---\n\n".join(parts)


def _is_ocr_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return isinstance(exc, OCR_ERROR_TYPES) and (
        OCR_ERROR_RE.search(message)
        or "ocr" in message
        or "scanned" in message
        or "imagebased" in message
        or "no extractable text" in message
    )


def _download_document(url: str) -> tuple[bytes, str]:
    try:
        response = requests.get(url, timeout=TELEGRAPH_REQUEST_TIMEOUT, headers={"User-Agent": "markdown-web"})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DocumentDownloadError from exc
    filename = Path(urlparse(url).path).name or "document"
    return response.content, filename


def _merge_metadata(markdown: str, supplied: SourceMetadata) -> tuple[str, SourceMetadata]:
    existing, body = split_front_matter(markdown.strip())
    merged = {**existing, **supplied.values()}
    if notify_telegram := _front_matter_notify_telegram(markdown):
        merged.setdefault("notify_telegram", notify_telegram)
    return add_front_matter(body, merged), SourceMetadata.model_validate(merged)


def prepare_content(request: SourceRequest) -> PreparedContent:
    """Extract and normalize a request into Markdown with YAML front matter."""
    if request.url:
        _require_source(request)
    if request.document is not None or (request.url and _is_document_url(request.url)):
        document, filename = (
            (request.document, request.filename)
            if request.document is not None
            else _download_document(request.url or "")
        )
        markdown = _convert_document(document or b"", filename)
        metadata = request.metadata
        if request.url and not metadata.url:
            metadata = metadata.model_copy(update={"url": request.url})
        if not metadata.title and filename:
            metadata = metadata.model_copy(update={"title": Path(filename).stem})
        front_matter, body = split_front_matter(markdown.strip())
        title = metadata.title or front_matter.get("title", "") or Path(filename).stem or "Document"
        fallback_text = markdown_to_text(body)
        intro = ""
    elif request.url:
        try:
            title, markdown, fallback_text, intro = extract_main_content(request.url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            raise SourceHTTPError(status) from exc
        metadata = request.metadata
    elif request.html is not None:
        title, markdown, fallback_text, intro = extract_main_content(request.html)
        metadata = request.metadata
    else:
        source = _require_source(request)
        front_matter, body = split_front_matter(source.strip())
        title = front_matter.get("title", "")
        markdown = source
        fallback_text = markdown_to_text(body)
        metadata = request.metadata
        intro = ""

    markdown, metadata = _merge_metadata(markdown, metadata)
    title = metadata.title or title
    return PreparedContent(
        title=title,
        markdown=markdown,
        fallback_text=fallback_text,
        metadata=metadata,
        intro=intro,
    )


def _publish_prepared_pages(prepared: PreparedContent, token: str, *, warm_cache: bool = True) -> TelegraphPages:
    chunks = split_markdown_pages(prepared.markdown, max_chars=TELEGRAPH_PAGE_MAX_CHARS)
    if len(chunks) == 1:
        url = create_page(
            title=prepared.title or None,
            content_markdown=prepared.markdown,
            fallback_text=prepared.fallback_text,
            source_url=prepared.metadata.url,
            author_name=prepared.metadata.author,
            access_token=token,
            warm_cache=warm_cache,
        )
        return TelegraphPages((url,), (prepared.markdown,))
    return create_pages(
        title=prepared.title or None,
        content_markdown=prepared.markdown,
        fallback_text=prepared.fallback_text,
        source_url=prepared.metadata.url,
        author_name=prepared.metadata.author,
        access_token=token,
        max_chars=TELEGRAPH_PAGE_MAX_CHARS,
        warm_cache=warm_cache,
    )


def _publish_prepared(prepared: PreparedContent, token: str, *, warm_cache: bool = True) -> str:
    return _publish_prepared_pages(prepared, token, warm_cache=warm_cache).urls[0]


def _publish_content(request: SourceRequest) -> str:
    """Publish request content to Telegraph and return its public URL."""
    prepared = prepare_content(request)
    token = telegraph_tokens.resolve(request.access_token)
    target = _publish_prepared(prepared, token)
    send_telegram_notifications(target, prepared.metadata.notify_telegram)
    return target


def _escape_markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _card_markdown(article: PublishedBriefArticle, link_marker: str) -> str:
    """Render a card image and leave its Telegraph link for the note's end."""
    title = _escape_markdown_text(article.content.title or article.source_url)
    parts: list[str] = []
    if image_url := article.content.metadata.image:
        parts.append(f"[![{title}]({image_url})]({article.telegraph_url})")
    parts.append(link_marker)
    return "\n\n".join(parts)


def _add_card_links_at_note_end(markdown: str, links: list[tuple[str, str]]) -> str:
    """Move generated Telegraph links below each note's editorial paragraphs."""
    for marker, url in links:
        before, found, after = markdown.partition(marker)
        if not found:
            continue
        boundary = re.search(r"\n\n---\n|\n## |\Z", after)
        end = boundary.start() if boundary else len(after)
        note = after[:end].strip()
        suffix = after[end:]
        markdown = f"{before.rstrip()}\n\n{note}\n\n[Leer en Telegraph]({url}){suffix}"
    return markdown


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
    pages = _publish_prepared_pages(content, token, warm_cache=warm_cache)
    return PublishedBriefArticle(
        source_url=source_url,
        content=content,
        telegraph_url=pages.urls[0],
        telegraph_urls=pages.urls,
        page_markdowns=pages.markdowns,
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
    links: list[tuple[str, str]] = []

    def expand_card(match: re.Match[str]) -> str:
        article = articles_by_source[match.group(1)]
        link_marker = f"<!-- telegraph-link-{len(links)} -->"
        links.append((link_marker, article.telegraph_url))
        return _card_markdown(article, link_marker)

    expanded_markdown = CARD_DIRECTIVE_RE.sub(
        expand_card,
        brief.markdown,
    )
    expanded_markdown = _add_card_links_at_note_end(expanded_markdown, links)
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
    page_markdown = article.page_markdowns[0] if article.page_markdowns else article.content.markdown
    page_urls = article.telegraph_urls or (article.telegraph_url,)
    return edit_page(
        path=urlparse(article.telegraph_url).path.lstrip("/"),
        title=article.content.title or None,
        content_markdown=(
            page_markdown + page_navigation(page_urls, 0) + _navigation_markdown(brief_url, previous_url, next_url)
        ),
        fallback_text=markdown_to_text(page_markdown),
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
    send_telegram_notifications(brief_url, brief.metadata.notify_telegram)
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
