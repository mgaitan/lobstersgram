"""The main URL-to-Markdown extraction pipeline."""

from __future__ import annotations

from logging import getLogger

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md
from readability import Document

from url_to_markdown.fetchers import (
    DEFAULT_REQUEST_TIMEOUT,
    fetch_arxiv_abstract,
    fetch_github_blob_markdown,
    fetch_github_readme,
    fetch_html,
)
from url_to_markdown.html import make_images_absolute, preprocess_figures
from url_to_markdown.markdown import (
    _make_markdown_links_absolute,
    _normalize_markdown_links,
    extract_intro,
    markdown_to_text,
)

logger = getLogger(__name__)


class ContentDownloadError(RuntimeError):
    """Raised when a URL cannot provide HTML content."""

    def __init__(self) -> None:
        super().__init__("Failed to download content")


def extract_main_content(
    url: str,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    min_content_length: int = 200,
    intro_min_length: int = 40,
) -> tuple[str, str, str, str]:
    """Return ``(title, markdown, fallback_text, intro)`` for *url*."""
    if github_blob_result := fetch_github_blob_markdown(url, request_timeout):
        title, markdown = github_blob_result
        fallback_text = markdown_to_text(markdown)
        return title, markdown, fallback_text, extract_intro(markdown, fallback_text, intro_min_length)

    if github_result := fetch_github_readme(url, request_timeout):
        title, markdown = github_result
        fallback_text = markdown_to_text(markdown)
        return title, markdown, fallback_text, extract_intro(markdown, fallback_text, intro_min_length)

    if arxiv_result := fetch_arxiv_abstract(url, request_timeout):
        title, markdown = arxiv_result
        fallback_text = markdown_to_text(markdown)
        return title, markdown, fallback_text, extract_intro(markdown, fallback_text, intro_min_length)

    downloaded = fetch_html(url, request_timeout)
    if not downloaded:
        raise ContentDownloadError

    content_html = ""
    title = url
    try:
        document = Document(downloaded)
        content_html = document.summary() or ""
        title = document.title() or url
    except Exception as exc:  # noqa: BLE001
        logger.warning("readability failed error=%s", exc)

    if not content_html or len(content_html.strip()) < min_content_length:
        content_html = downloaded

    content_html = preprocess_figures(make_images_absolute(content_html, url))
    extracted_markdown = html_to_md(content_html)
    extracted_markdown = _normalize_markdown_links(extracted_markdown)
    extracted_markdown = _make_markdown_links_absolute(extracted_markdown, url)
    fallback_text = BeautifulSoup(content_html, "html.parser").get_text(separator="\n").strip()
    intro = extract_intro(extracted_markdown, fallback_text, intro_min_length)
    return title, extracted_markdown, fallback_text, intro
