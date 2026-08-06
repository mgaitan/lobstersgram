"""Tests for content extraction and normalization helpers."""

# ruff: noqa: F401

from __future__ import annotations

import base64
import unittest.mock

import requests
from bs4 import BeautifulSoup
from url_to_markdown import (
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
    strip_leading_title_heading,
)
from url_to_markdown import extractor as extractor_module
from url_to_markdown import html as html_module
from url_to_markdown import markdown as markdown_module

BASE = "https://example.com/articles/my-post/"

# ---------------------------------------------------------------------------
# make_images_absolute tests
# ---------------------------------------------------------------------------


def test_absolute_http_src_unchanged() -> None:
    """An already-absolute http:// src is kept as-is."""
    html = '<p><img src="https://cdn.example.com/img.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/img.png"' in result


def test_relative_root_src_becomes_absolute() -> None:
    """A root-relative src (e.g. /images/foo.png) is resolved against base_url."""
    html = '<p><img src="/images/foo.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/images/foo.png"' in result


def test_relative_path_src_becomes_absolute() -> None:
    """A relative path src (e.g. ../img/bar.jpg) is resolved against base_url."""
    html = '<p><img src="../img/bar.jpg"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/articles/img/bar.jpg"' in result


def test_data_uri_image_is_removed() -> None:
    """Images with data: URIs are removed entirely."""
    html = '<p>before</p><p><img src="data:image/png;base64,abc"/></p><p>after</p>'
    result = make_images_absolute(html, BASE)
    assert "<img" not in result
    assert "before" in result
    assert "after" in result


def test_empty_src_image_is_removed() -> None:
    """Images with empty src are removed entirely."""
    html = '<p><img src=""/></p>'
    result = make_images_absolute(html, BASE)
    assert "<img" not in result


def test_missing_src_image_is_removed() -> None:
    """Images with no src attribute are removed entirely."""
    html = "<p><img/></p>"
    result = make_images_absolute(html, BASE)
    assert "<img" not in result


def test_mixed_images_keeps_only_valid() -> None:
    """Valid and invalid images in the same HTML: only valid ones are kept."""
    html = '<p><img src="/a.png"/><img src="data:image/png;base64,xyz"/><img src="https://other.com/b.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://example.com/a.png"' in result
    assert 'src="https://other.com/b.png"' in result
    assert "data:" not in result


def test_no_images_is_noop() -> None:
    """HTML with no images is returned unchanged (modulo parser normalisation)."""
    html = "<p>just text</p>"
    result = make_images_absolute(html, BASE)
    assert "just text" in result
    assert "<img" not in result


def test_data_src_used_when_src_missing() -> None:
    """data-src is used as the image URL when src is absent (lazy-loading)."""
    html = '<p><img data-src="https://cdn.example.com/lazy.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/lazy.png"' in result


def test_data_src_used_when_src_is_data_uri() -> None:
    """data-src is preferred over a data-URI placeholder in src."""
    html = '<p><img src="data:image/gif;base64,R0lGOD" data-src="https://cdn.example.com/real.png"/></p>'
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/real.png"' in result
    assert "data:" not in result


def test_srcset_highest_width_used_when_no_src() -> None:
    """When src is absent the highest-width srcset candidate is used."""
    html = (
        '<p><img srcset="https://cdn.example.com/img-320.png 320w,'
        " https://cdn.example.com/img-640.png 640w,"
        ' https://cdn.example.com/img-1280.png 1280w"/></p>'
    )
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/img-1280.png"' in result


def test_srcset_fallback_when_src_is_data_uri() -> None:
    """A data-URI src is replaced by the best srcset candidate."""
    html = (
        '<p><img src="data:image/gif;base64,R0lGOD"'
        ' srcset="https://cdn.example.com/img-320.png 320w,'
        ' https://cdn.example.com/img-1024.png 1024w"/></p>'
    )
    result = make_images_absolute(html, BASE)
    assert 'src="https://cdn.example.com/img-1024.png"' in result
    assert "data:" not in result


# ---------------------------------------------------------------------------
# preprocess_figures tests
# ---------------------------------------------------------------------------


def test_preprocess_figures_converts_text_figure_to_blockquote() -> None:
    """A figure containing text paragraphs is converted to a blockquote."""
    html = "<figure><div><p>This is a quote</p></div></figure>"
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None
    assert soup.find("figure") is None
    assert "This is a quote" in result


def test_preprocess_figures_image_in_div_wrapper_unchanged() -> None:
    """A figure whose only <div> wraps an image (no text) is NOT converted.

    Substack and similar sites wrap images in <div> containers inside <figure>.
    These should remain as figures so that the image is preserved.
    """
    html = (
        "<figure>"
        '<div class="image-container">'
        '<img src="https://example.com/photo.png" alt="photo"/>'
        "</div>"
        "<figcaption>A photo</figcaption>"
        "</figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None, "image figure should not be converted to blockquote"
    assert soup.find("blockquote") is None
    assert soup.find("img") is not None, "image must be preserved"


def test_preprocess_figures_substack_style_image_figure_unchanged() -> None:
    """Substack-style nested image figure is NOT converted to a blockquote."""
    html = (
        "<figure>"
        '<a class="image-link" href="https://example.com/">'
        '<div class="image2-inset">'
        '<img src="https://cdn.example.com/img.png"'
        ' srcset="https://cdn.example.com/img-640.png 640w,'
        ' https://cdn.example.com/img-1280.png 1280w"'
        ' alt="diagram"/>'
        "</div>"
        "</a>"
        "<figcaption></figcaption>"
        "</figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None, "image figure should not be converted"
    assert soup.find("blockquote") is None
    assert soup.find("img") is not None, "image must be preserved"


def test_preprocess_figures_image_only_figure_unchanged() -> None:
    """A figure containing only an image is NOT converted to a blockquote."""
    html = '<figure><img src="https://example.com/img.png" alt="test"/></figure>'
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None
    assert soup.find("blockquote") is None


def test_preprocess_figures_image_with_figcaption_only_unchanged() -> None:
    """A figure with only an image and figcaption is not converted."""
    html = '<figure><img src="https://example.com/img.png"/><figcaption>Caption</figcaption></figure>'
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("figure") is not None
    assert soup.find("blockquote") is None


def test_preprocess_figures_figcaption_moved_after_blockquote() -> None:
    """The figcaption is placed after the blockquote, not inside it."""
    html = (
        "<figure><div><p>Quote text</p></div><figcaption><a href='https://example.com'>Author</a></figcaption></figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    blockquote = soup.find("blockquote")
    figcaption = soup.find("figcaption")
    assert blockquote is not None
    assert figcaption is not None
    # figcaption should not be inside blockquote
    assert figcaption.find_parent("blockquote") is None
    assert blockquote.find("figcaption") is None
    # figcaption text is still present
    assert "Author" in result


def test_preprocess_figures_no_figures_is_noop() -> None:
    """HTML without any <figure> elements is returned unchanged."""
    html = "<p>Just a paragraph</p>"
    result = preprocess_figures(html)
    assert "Just a paragraph" in result
    assert "<figure" not in result
    assert "<blockquote" not in result


def test_preprocess_figures_github_quote_example() -> None:
    """Real-world GitHub quote figure is correctly converted to a blockquote."""
    html = (
        '<figure class="not-prose">'
        '<a href="https://github.com/example" rel="noopener noreferrer">'
        "<svg></svg>"
        "</a>"
        '<div class="gh-quote-body">'
        "<p>I have done everything you asked.</p>"
        "</div>"
        "<figcaption>"
        '<img src="https://avatars.githubusercontent.com/user?size=32" alt="user" width="24"/>'
        '<a href="https://github.com/example">@user · Feb 13, 2021</a>'
        "</figcaption>"
        "</figure>"
    )
    result = preprocess_figures(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None
    assert soup.find("figure") is None
    assert "I have done everything you asked." in result
    assert "@user" in result


def test_preprocess_figures_preserves_quote_text_content() -> None:
    """All text content within the figure body is preserved in the blockquote."""
    html = "<figure><p>First sentence.</p><p>Second sentence.</p></figure>"
    result = preprocess_figures(html)
    assert "First sentence." in result
    assert "Second sentence." in result
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("blockquote") is not None


# ---------------------------------------------------------------------------
# fetch_html encoding tests
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for ``requests.Response`` used by ``fetch_html`` tests.

    Only ``content`` (raw bytes) and ``raise_for_status`` are required by the
    current implementation, which passes ``r.content`` directly to
    ``UnicodeDammit``.  The ``encoding`` and ``apparent_encoding`` attributes
    are kept for reference but are no longer read by ``fetch_html``.
    """

    def __init__(self, content: bytes, initial_encoding: str = "iso-8859-1", apparent_encoding: str = "utf-8") -> None:
        self.content = content
        self.encoding: str = initial_encoding
        self.apparent_encoding = apparent_encoding

    def raise_for_status(self) -> None:
        pass

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


def test_fetch_html_uses_apparent_encoding_for_utf8_content() -> None:
    """fetch_html must decode UTF-8 content correctly even when the server does not
    declare a charset in the Content-Type header.

    Without an explicit charset, requests defaults to ISO-8859-1, which mangles
    multi-byte UTF-8 characters such as the em-dash (U+2014) into â€".
    UnicodeDammit falls back to charset_normalizer detection for content with
    no <meta charset> declaration and should still detect UTF-8 correctly.
    """
    em_dash_html = "<p>Hello \u2014 world</p>"
    utf8_bytes = em_dash_html.encode("utf-8")

    fake_response = _FakeResponse(content=utf8_bytes)

    with unittest.mock.patch("url_to_markdown.fetchers.requests.get", return_value=fake_response):
        result = fetch_html("https://example.com/article")

    assert result is not None
    assert "\u2014" in result, "em-dash should be preserved, not mangled"
    assert "â€" not in (result or ""), "mojibake should not appear in the output"


def test_fetch_html_decodes_curly_apostrophe_via_meta_charset() -> None:
    """fetch_html must correctly decode curly apostrophes (U+2019) in pages that
    declare <meta charset="utf-8"> even when charset_normalizer would incorrectly
    identify the encoding as ISO-8859-1.

    Mostly-ASCII pages with only a handful of multi-byte characters (e.g. a curly
    apostrophe in "We've been doing") can fool pure statistical detection into
    returning ISO-8859-1, causing mojibake: the three UTF-8 bytes \\xE2\\x80\\x99 for
    U+2019 are decoded as "â" + two non-printable control chars, yielding "Weâve".
    Using UnicodeDammit with is_html=True ensures the <meta charset> declaration is
    consulted first, producing the correct result.
    """
    apostrophe_html = '<html><head><meta charset="utf-8"/></head><body><p>We\u2019ve been doing</p></body></html>'
    utf8_bytes = apostrophe_html.encode("utf-8")

    # Simulate charset_normalizer failing to detect UTF-8 for mostly-ASCII content.
    # Note: apparent_encoding is no longer consulted by fetch_html; it is kept
    # here only as documentation of the failure mode this test addresses.
    fake_response = _FakeResponse(content=utf8_bytes)

    with unittest.mock.patch("url_to_markdown.fetchers.requests.get", return_value=fake_response):
        result = fetch_html("https://example.com/article")

    assert result is not None
    assert "\u2019" in result, "curly apostrophe should be preserved, not mangled"
    assert "Weâ" not in (result or ""), "mojibake must not appear in the output"
