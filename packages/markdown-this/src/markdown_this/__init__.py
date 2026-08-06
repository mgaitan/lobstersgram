"""Convert web pages and supported special URLs to Markdown."""

from markdown_this.extractor import ContentDownloadError, extract_main_content
from markdown_this.fetchers import (
    _github_repo_match,
    fetch_arxiv_abstract,
    fetch_github_blob_markdown,
    fetch_github_readme,
    fetch_html,
    fetch_url,
)
from markdown_this.html import make_images_absolute, preprocess_figures
from markdown_this.markdown import (
    _extract_leading_heading,
    _is_html_badge_block,
    _make_markdown_images_absolute,
    _make_markdown_links_absolute,
    _normalize_markdown_links,
    _strip_badge_paragraphs,
    extract_intro,
    markdown_to_text,
    strip_leading_title_heading,
)

__all__ = [
    "ContentDownloadError",
    "_extract_leading_heading",
    "_github_repo_match",
    "_is_html_badge_block",
    "_make_markdown_images_absolute",
    "_make_markdown_links_absolute",
    "_normalize_markdown_links",
    "_strip_badge_paragraphs",
    "extract_intro",
    "extract_main_content",
    "fetch_arxiv_abstract",
    "fetch_github_blob_markdown",
    "fetch_github_readme",
    "fetch_html",
    "fetch_url",
    "make_images_absolute",
    "markdown_to_text",
    "preprocess_figures",
    "strip_leading_title_heading",
]
