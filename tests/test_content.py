"""Tests for content extraction and normalization helpers."""

from __future__ import annotations

import os

from bs4 import BeautifulSoup

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstergram.content import make_images_absolute, preprocess_figures

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
