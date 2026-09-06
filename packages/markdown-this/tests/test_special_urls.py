"""Tests for content extraction and normalization helpers."""

# ruff: noqa: F401

from __future__ import annotations

import base64
import unittest.mock

import requests
from bs4 import BeautifulSoup
from markdown_this import (
    ContentDownloadError,
    _extract_leading_heading,
    _github_repo_match,
    _is_html_badge_block,
    _make_markdown_images_absolute,
    _make_markdown_links_absolute,
    _normalize_markdown_links,
    _strip_badge_paragraphs,
    extract_intro,
    fetch_arxiv_abstract,
    fetch_github_blob_markdown,
    fetch_github_readme,
    fetch_html,
    fetch_url,
    make_images_absolute,
    markdown_to_text,
    preprocess_figures,
)
from markdown_this import extractor as extractor_module
from markdown_this import html as html_module
from markdown_this import markdown as markdown_module
from pytest_mock import MockerFixture

BASE = "https://example.com/articles/my-post/"

# fetch_github_blob_markdown tests
# ---------------------------------------------------------------------------


def _make_fake_blob_api_get(
    content_md: str, name: str = "file.md", download_url: str = "", *, mocker: MockerFixture
) -> object:
    """Return a mock for ``requests.get`` that returns a GitHub Contents API response."""

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "name": name,
                "content": base64.b64encode(content_md.encode()).decode() + "\n",
                "download_url": download_url,
            }

    return mocker.patch("markdown_this.fetchers.requests.get", return_value=_FakeResp())


def test_fetch_github_blob_markdown_extracts_title_from_h2(*, mocker: MockerFixture) -> None:
    """Title is taken from the first h2 heading; heading is stripped from content."""
    blob_md = "## Embedding EYG in Gleam programs\n\nEYG is type safe scripting."
    url = "https://github.com/CrowdHailer/eyg-lang/blob/main/guides/embedding_in_gleam.md"
    _make_fake_blob_api_get(blob_md, name="embedding_in_gleam.md", mocker=mocker)
    result = fetch_github_blob_markdown(url)
    assert result is not None
    title, markdown = result
    assert title == "Embedding EYG in Gleam programs"
    assert "## Embedding EYG" not in markdown
    assert "EYG is type safe scripting." in markdown


def test_fetch_github_blob_markdown_extracts_title_from_h1(*, mocker: MockerFixture) -> None:
    """Title is taken from an h1 heading when present."""
    blob_md = "# Getting Started\n\nWelcome to the guide."
    url = "https://github.com/owner/repo/blob/main/docs/guide.md"
    _make_fake_blob_api_get(blob_md, name="guide.md", mocker=mocker)
    result = fetch_github_blob_markdown(url)
    assert result is not None
    title, markdown = result
    assert title == "Getting Started"
    assert "# Getting Started" not in markdown
    assert "Welcome to the guide." in markdown


def test_fetch_github_blob_markdown_fallback_title_when_no_heading(*, mocker: MockerFixture) -> None:
    """Falls back to owner/repo/path title when the file has no heading."""
    blob_md = "Just some plain content without a heading."
    url = "https://github.com/owner/repo/blob/main/notes.md"
    _make_fake_blob_api_get(blob_md, name="notes.md", mocker=mocker)
    result = fetch_github_blob_markdown(url)
    assert result is not None
    title, markdown = result
    assert title == "owner/repo/notes.md"
    assert "Just some plain content" in markdown


def test_fetch_github_blob_markdown_non_markdown_url_returns_none() -> None:
    """Returns None for GitHub blob URLs that are not Markdown files."""
    url = "https://github.com/owner/repo/blob/main/script.py"
    result = fetch_github_blob_markdown(url)
    assert result is None


def test_fetch_github_blob_markdown_non_github_url_returns_none() -> None:
    """Returns None for non-GitHub URLs."""
    result = fetch_github_blob_markdown("https://example.com/article.md")
    assert result is None


def test_fetch_github_blob_markdown_repo_root_url_returns_none() -> None:
    """Returns None for GitHub repository root URLs (handled by fetch_github_readme)."""
    result = fetch_github_blob_markdown("https://github.com/owner/repo")
    assert result is None


def test_fetch_github_blob_markdown_request_failure_returns_none(*, mocker: MockerFixture) -> None:
    """Returns None when the raw content fetch fails."""
    url = "https://github.com/owner/repo/blob/main/file.md"
    mocker.patch(
        "markdown_this.fetchers.requests.get",
        side_effect=requests.RequestException("network error"),
    )
    result = fetch_github_blob_markdown(url)
    assert result is None


def test_fetch_github_blob_markdown_resolves_relative_images(*, mocker: MockerFixture) -> None:
    """Relative image URLs in the raw Markdown are resolved to absolute URLs."""
    blob_md = "# Guide\n\n![diagram](./images/diagram.png)\n\nSome text."
    url = "https://github.com/owner/repo/blob/main/docs/guide.md"
    download_url = "https://raw.githubusercontent.com/owner/repo/main/docs/guide.md"
    _make_fake_blob_api_get(blob_md, name="guide.md", download_url=download_url, mocker=mocker)
    result = fetch_github_blob_markdown(url)
    assert result is not None
    _, markdown = result
    assert "https://raw.githubusercontent.com/owner/repo/main/docs/images/diagram.png" in markdown
    assert "./images/diagram.png" not in markdown


# ---------------------------------------------------------------------------
# fetch_arxiv_abstract tests
# ---------------------------------------------------------------------------

_ARXIV_ABS_HTML = """
<html>
<head><title>[2604.07902] Optimization of 32-bit Unsigned Division by Constants on 64-bit Targets</title></head>
<body>
<h1 class="title mathjax"><span class="descriptor">Title:</span>
Optimization of 32-bit Unsigned Division by Constants on 64-bit Targets</h1>
<div class="authors"><span class="descriptor">Authors:</span>
<a href="/search/?searchtype=author&amp;query=Smith">John Smith</a>,
<a href="/search/?searchtype=author&amp;query=Doe">Jane Doe</a></div>
<blockquote class="abstract mathjax">
<span class="descriptor">Abstract:</span>
We present an optimization technique for 32-bit unsigned integer division by constants on 64-bit targets.
</blockquote>
</body>
</html>
"""


def _make_fake_arxiv_get(html: str, *, mocker: MockerFixture) -> unittest.mock.MagicMock:
    class _FakeResp:
        content = html.encode()

        def raise_for_status(self) -> None:
            pass

    return mocker.patch("markdown_this.fetchers.requests.get", return_value=_FakeResp())


def test_fetch_arxiv_abstract_returns_title_authors_and_abstract(*, mocker: MockerFixture) -> None:
    """fetch_arxiv_abstract extracts title, authors, and abstract from an arXiv page."""
    url = "https://arxiv.org/abs/2604.07902"
    _make_fake_arxiv_get(_ARXIV_ABS_HTML, mocker=mocker)
    result = fetch_arxiv_abstract(url)
    assert result is not None
    title, markdown = result
    assert "Optimization of 32-bit Unsigned Division" in title
    assert "John Smith" in markdown
    assert "Jane Doe" in markdown
    assert "optimization technique" in markdown
    assert "**Authors:**" in markdown


def test_fetch_arxiv_abstract_non_arxiv_url_returns_none() -> None:
    """Returns None immediately for non-arXiv URLs."""
    result = fetch_arxiv_abstract("https://example.com/abs/1234")
    assert result is None


def test_fetch_arxiv_abstract_abs_prefix_required() -> None:
    """Returns None for arxiv.org URLs that are not /abs/ paths."""
    result = fetch_arxiv_abstract("https://arxiv.org/pdf/2604.07902")
    assert result is None


def test_fetch_arxiv_abstract_request_failure_returns_none(*, mocker: MockerFixture) -> None:
    """Returns None when the HTTP request fails."""
    url = "https://arxiv.org/abs/2604.07902"
    mocker.patch(
        "markdown_this.fetchers.requests.get",
        side_effect=requests.RequestException("network error"),
    )
    result = fetch_arxiv_abstract(url)
    assert result is None


def test_fetch_arxiv_abstract_strips_descriptor_spans(*, mocker: MockerFixture) -> None:
    """The 'Title:', 'Authors:', and 'Abstract:' descriptor spans are stripped."""
    url = "https://arxiv.org/abs/2604.07902"
    _make_fake_arxiv_get(_ARXIV_ABS_HTML, mocker=mocker)
    result = fetch_arxiv_abstract(url)
    assert result is not None
    title, markdown = result
    # The <span class="descriptor">Title:</span> text should not appear in the title.
    assert not title.startswith("Title:")
    # The abstract descriptor "Abstract:" should not appear in the blockquote text.
    assert "> Abstract:" not in markdown
    assert "Optimization of 32-bit" in title


def test_fetch_arxiv_abstract_older_style_id(*, mocker: MockerFixture) -> None:
    """Older-style arXiv IDs with a category prefix are matched."""
    html = """
<html><body>
<h1 class="title mathjax"><span class="descriptor">Title:</span> A Classic Paper</h1>
<div class="authors"><span class="descriptor">Authors:</span> <a>Old Author</a></div>
<blockquote class="abstract mathjax"><span class="descriptor">Abstract:</span>
This is a classic result.</blockquote>
</body></html>
"""
    url = "https://arxiv.org/abs/hep-th/9711200"
    _make_fake_arxiv_get(html, mocker=mocker)
    result = fetch_arxiv_abstract(url)
    assert result is not None
    title, markdown = result
    assert title == "A Classic Paper"
    assert "Old Author" in markdown
    assert "classic result" in markdown


# ---------------------------------------------------------------------------
# remaining pipeline and edge-case coverage
# ---------------------------------------------------------------------------


def test_fetch_url_returns_redirect_target(*, mocker: MockerFixture) -> None:
    response = mocker.Mock(url="https://example.com/final", status_code=200)
    mocker.patch("markdown_this.fetchers.requests.get", return_value=response)
    result = fetch_url("https://example.com/start", timeout=3)
    assert result == "https://example.com/final"


def test_fetch_html_falls_back_to_latin1_when_encoding_detection_has_no_result(*, mocker: MockerFixture) -> None:
    response = mocker.Mock(content=b"\xff")
    mocker.patch("markdown_this.fetchers.requests.get", return_value=response)
    mocker.patch("markdown_this.fetchers.UnicodeDammit", return_value=mocker.Mock(unicode_markup=""))
    result = fetch_html("https://example.com/article")
    assert result == "ÿ"


def test_fetch_github_readme_keeps_default_title_when_metadata_request_fails(*, mocker: MockerFixture) -> None:
    readme = {
        "name": "README.md",
        "content": base64.b64encode(b"A useful README.").decode(),
        "download_url": "",
    }
    responses = [requests.RequestException("metadata failed"), mocker.Mock(**{"json.return_value": readme})]
    responses[1].raise_for_status = mocker.Mock()
    mocker.patch("markdown_this.fetchers.requests.get", side_effect=responses)
    result = fetch_github_readme("https://github.com/owner/repo")
    assert result == ("owner/repo", "A useful README.")


def test_fetch_arxiv_abstract_uses_fallback_fields_and_handles_empty_pages(*, mocker: MockerFixture) -> None:
    html = '<div class="authors">Authors: Plain Author</div>'
    mocker.patch("markdown_this.fetchers.fetch_html", return_value=html)
    result = fetch_arxiv_abstract("https://arxiv.org/abs/1234")
    assert result == ("1234", "**Authors:** Authors: Plain Author")
    mocker.patch("markdown_this.fetchers.fetch_html", return_value="")
    assert fetch_arxiv_abstract("https://arxiv.org/abs/1234") is None
    mocker.patch("markdown_this.fetchers.fetch_html", return_value="<html></html>")
    assert fetch_arxiv_abstract("https://arxiv.org/abs/1234") is None


def test_make_images_absolute_skips_empty_srcset_and_removes_non_http_images() -> None:
    assert html_module._best_src_for_img(BeautifulSoup('<img srcset=", " />', "html.parser").img) == ""
    result = make_images_absolute('<img src="ftp://example.com/image.png">', BASE)
    assert "image.png" not in result


def test_markdown_helpers_cover_invalid_links_and_intro_fallback() -> None:
    assert _make_markdown_links_absolute("[site](javascript:alert(1))", BASE) == "[site](javascript:alert(1))"
    assert _normalize_markdown_links("[\n\ntext](https://example.com)") == "[text](https://example.com)"
    assert extract_intro("short", "fallback line", min_length=40) == "fallback line"
    assert markdown_module.extract_intro("", "") == ""
    assert _is_html_badge_block("<p><a><span>unexpected</span></a></p>") is False
    assert _is_html_badge_block("<p><span>unexpected</span></p>") is False


def test_extract_main_content_handles_special_and_generic_paths(*, mocker: MockerFixture) -> None:
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (mocker.Mock(return_value=("Blob", "# body\n\nBlob content")),),
    )
    assert extractor_module.extract_main_content("https://github.com/owner/repo/blob/main/a.md")[0] == "Blob"
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (
            mocker.Mock(return_value=None),
            mocker.Mock(return_value=("Repo", "Repo content")),
        ),
    )
    result = extractor_module.extract_main_content("https://github.com/owner/repo")
    assert result[0] == "Repo"
    metadata, body = extractor_module.split_front_matter(result[1])
    assert metadata == {"title": "Repo", "url": "https://github.com/owner/repo"}
    assert body == "Repo content"
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (
            mocker.Mock(return_value=None),
            mocker.Mock(return_value=("Repo", "# Repo\n\nRepo content")),
        ),
    )
    result = extractor_module.extract_main_content("https://github.com/owner/repo")
    metadata, body = extractor_module.split_front_matter(result[1])
    assert metadata == {"title": "Repo", "url": "https://github.com/owner/repo"}
    assert body == "# Repo\n\nRepo content"
    assert result[2] == "Repo\n\nRepo content"
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (mocker.Mock(return_value=("owner/repo/README.md", "---\ntitle: Declared title\n---\n\nREADME content")),),
    )
    result = extractor_module.extract_main_content("https://github.com/owner/repo/blob/main/README.md")
    metadata, body = extractor_module.split_front_matter(result[1])
    assert result[0] == "Declared title"
    assert metadata["title"] == "Declared title"
    assert body == "README content"
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (
            mocker.Mock(return_value=None),
            mocker.Mock(return_value=("owner/repo", "---\ntitle: Declared README title\n---\n\nREADME content")),
        ),
    )
    result = extractor_module.extract_main_content("https://github.com/owner/repo")
    assert result[0] == "Declared README title"
    assert result[2] == "README content"
    mocker.patch.object(
        extractor_module,
        "SPECIAL_URL_EXTRACTORS",
        (
            mocker.Mock(return_value=None),
            mocker.Mock(return_value=None),
            mocker.Mock(return_value=("Paper", "Paper content")),
        ),
    )
    assert extractor_module.extract_main_content("https://arxiv.org/abs/1234")[0] == "Paper"


def test_extract_main_content_generic_fallback_and_download_error(*, mocker: MockerFixture) -> None:
    mocker.patch.object(extractor_module, "SPECIAL_URL_EXTRACTORS", (mocker.Mock(return_value=None),))
    mocker.patch("markdown_this.extractor.fetch_html", return_value="<html><p>Generic article body.</p></html>")
    mocker.patch.object(extractor_module, "Document", side_effect=ValueError("bad document"))
    result = extractor_module.extract_main_content("https://example.com/article", intro_min_length=100)
    assert result[0] == "https://example.com/article"
    assert "Generic article body." in result[1]
    assert result[3] == "Generic article body."

    document = mocker.Mock(
        summary=mocker.Mock(return_value="<article>Long extracted content.</article>"),
        title=mocker.Mock(return_value="Extracted title"),
    )
    mocker.patch.object(extractor_module, "SPECIAL_URL_EXTRACTORS", (mocker.Mock(return_value=None),))
    mocker.patch("markdown_this.extractor.fetch_html", return_value="<html>source</html>")
    mocker.patch.object(extractor_module, "Document", return_value=document)
    result = extractor_module.extract_main_content("https://example.com/article")
    assert result[0] == "Extracted title"
    mocker.patch.object(extractor_module, "SPECIAL_URL_EXTRACTORS", (mocker.Mock(return_value=None),))
    mocker.patch("markdown_this.extractor.fetch_html", return_value=None)
    try:
        extractor_module.extract_main_content("https://example.com/missing")
    except ContentDownloadError as exc:
        assert str(exc) == "Failed to download content"
    else:
        raise ContentDownloadError
