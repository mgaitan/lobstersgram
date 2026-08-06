"""The main URL-to-Markdown extraction pipeline."""

from __future__ import annotations

import urllib.parse
from logging import getLogger
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md
from readability import Document

from markdown_this.fetchers import (
    DEFAULT_REQUEST_TIMEOUT,
    fetch_arxiv_abstract,
    fetch_github_blob_markdown,
    fetch_github_readme,
    fetch_html,
)
from markdown_this.html import make_images_absolute, preprocess_figures
from markdown_this.markdown import (
    _make_markdown_links_absolute,
    _normalize_markdown_links,
    extract_intro,
    markdown_to_text,
)
from markdown_this.metadata import add_front_matter, extract_html_metadata, split_front_matter

logger = getLogger(__name__)


class ContentDownloadError(RuntimeError):
    """Raised when a content source cannot provide HTML content."""

    def __init__(self) -> None:
        super().__init__("Failed to download content")


def _finalize_content(
    title: str,
    markdown: str,
    fallback_text: str | None,
    intro_min_length: int,
    metadata: dict[str, str] | None = None,
) -> tuple[str, str, str, str]:
    """Normalize extracted Markdown and derive its fallback text and intro."""
    front_matter, content_markdown = split_front_matter(markdown.strip())
    resolved_title = front_matter.get("title") or title
    content_metadata = {**front_matter, **(metadata or {}), "title": resolved_title}
    content_fallback = fallback_text if fallback_text is not None else markdown_to_text(content_markdown)
    intro = extract_intro(content_markdown, content_fallback, intro_min_length)
    return resolved_title, add_front_matter(content_markdown, content_metadata), content_fallback, intro


def _is_http_url(source: str) -> bool:
    parsed = urllib.parse.urlparse(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _existing_path(source: str) -> Path | None:
    if source.lstrip().startswith("<"):
        return None
    path = Path(source)
    return path if path.is_file() else None


def _extract_html_content(  # noqa: PLR0913
    content_html: str,
    source_label: str,
    base_url: str,
    source_url: str,
    min_content_length: int,
    intro_min_length: int,
) -> tuple[str, str, str, str]:
    if not content_html:
        raise ContentDownloadError

    content_html_for_markdown = ""
    title = source_label
    try:
        document = Document(content_html)
        content_html_for_markdown = document.summary() or ""
        title = document.title() or source_label
    except Exception as exc:  # noqa: BLE001
        logger.warning("readability failed error=%s", exc)

    if not content_html_for_markdown or len(content_html_for_markdown.strip()) < min_content_length:
        content_html_for_markdown = content_html

    content_html_for_markdown = preprocess_figures(make_images_absolute(content_html_for_markdown, base_url))
    extracted_markdown = html_to_md(content_html_for_markdown)
    extracted_markdown = _normalize_markdown_links(extracted_markdown)
    extracted_markdown = _make_markdown_links_absolute(extracted_markdown, base_url)
    fallback_text = BeautifulSoup(content_html_for_markdown, "html.parser").get_text(separator="\n").strip()
    metadata = extract_html_metadata(content_html)
    if source_url:
        metadata["url"] = source_url
    return _finalize_content(title, extracted_markdown, fallback_text, intro_min_length, metadata)


def _extract_url_content(
    url: str,
    request_timeout: int,
    min_content_length: int,
    intro_min_length: int,
) -> tuple[str, str, str, str]:
    if github_blob_result := fetch_github_blob_markdown(url, request_timeout):
        title, markdown = github_blob_result
        return _finalize_content(title, markdown, None, intro_min_length, {"url": url})

    if github_result := fetch_github_readme(url, request_timeout):
        title, markdown = github_result
        return _finalize_content(title, markdown, None, intro_min_length, {"url": url})

    if arxiv_result := fetch_arxiv_abstract(url, request_timeout):
        title, markdown = arxiv_result
        return _finalize_content(title, markdown, None, intro_min_length, {"url": url})

    downloaded = fetch_html(url, request_timeout)
    return _extract_html_content(downloaded or "", url, url, url, min_content_length, intro_min_length)


def extract_main_content(
    source: Path | str,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    min_content_length: int = 200,
    intro_min_length: int = 40,
) -> tuple[str, str, str, str]:
    """Return ``(title, markdown, fallback_text, intro)`` for a URL, path, or HTML."""
    if isinstance(source, Path):
        return _extract_html_content(
            source.read_text(encoding="utf-8"),
            source.stem,
            source.as_uri(),
            "",
            min_content_length,
            intro_min_length,
        )

    if _is_http_url(source):
        return _extract_url_content(source, request_timeout, min_content_length, intro_min_length)

    if path := _existing_path(source):
        return _extract_html_content(
            path.read_text(encoding="utf-8"),
            path.stem,
            path.as_uri(),
            "",
            min_content_length,
            intro_min_length,
        )

    return _extract_html_content(source, "HTML content", "", "", min_content_length, intro_min_length)
