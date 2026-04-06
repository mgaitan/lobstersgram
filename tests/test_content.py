"""Tests for content extraction and normalization helpers."""

from __future__ import annotations

import base64
import os
import unittest.mock

from bs4 import BeautifulSoup

# Provide required env vars before importing the package (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from lobstergram.content import (
    _github_repo_match,
    _make_markdown_images_absolute,
    _strip_badge_paragraphs,
    extract_intro,
    fetch_github_readme,
    fetch_html,
    make_images_absolute,
    markdown_to_text,
    preprocess_figures,
)

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
        '<figure>'
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

    with unittest.mock.patch("lobstergram.content.requests.get", return_value=fake_response):
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
    apostrophe_html = (
        '<html><head><meta charset="utf-8"/></head>'
        "<body><p>We\u2019ve been doing</p></body></html>"
    )
    utf8_bytes = apostrophe_html.encode("utf-8")

    # Simulate charset_normalizer failing to detect UTF-8 for mostly-ASCII content.
    # Note: apparent_encoding is no longer consulted by fetch_html; it is kept
    # here only as documentation of the failure mode this test addresses.
    fake_response = _FakeResponse(content=utf8_bytes)

    with unittest.mock.patch("lobstergram.content.requests.get", return_value=fake_response):
        result = fetch_html("https://example.com/article")

    assert result is not None
    assert "\u2019" in result, "curly apostrophe should be preserved, not mangled"
    assert "Weâ" not in (result or ""), "mojibake must not appear in the output"


# ---------------------------------------------------------------------------
# _github_repo_match tests
# ---------------------------------------------------------------------------


def test_github_repo_match_plain_url() -> None:
    """A plain https://github.com/owner/repo URL matches."""
    m = _github_repo_match("https://github.com/hauntsaninja/git_bayesect")
    assert m is not None
    assert m.group("owner") == "hauntsaninja"
    assert m.group("repo") == "git_bayesect"


def test_github_repo_match_trailing_slash() -> None:
    """Trailing slash is accepted."""
    m = _github_repo_match("https://github.com/owner/repo/")
    assert m is not None


def test_github_repo_match_http_scheme() -> None:
    """http:// scheme is also accepted."""
    m = _github_repo_match("http://github.com/owner/repo")
    assert m is not None


def test_github_repo_match_issues_url_rejected() -> None:
    """URLs with sub-paths (issues, PRs, etc.) do not match."""
    assert _github_repo_match("https://github.com/owner/repo/issues") is None


def test_github_repo_match_blob_url_rejected() -> None:
    """File blob URLs do not match."""
    assert _github_repo_match("https://github.com/owner/repo/blob/main/README.md") is None


def test_github_repo_match_non_github_rejected() -> None:
    """Non-GitHub URLs do not match."""
    assert _github_repo_match("https://example.com/owner/repo") is None


def test_github_repo_match_user_profile_rejected() -> None:
    """A GitHub user profile URL (single path segment) does not match."""
    assert _github_repo_match("https://github.com/owner") is None


# ---------------------------------------------------------------------------
# _make_markdown_images_absolute tests
# ---------------------------------------------------------------------------

_RAW_BASE = "https://raw.githubusercontent.com/owner/repo/main/"


def test_make_markdown_images_absolute_relative_path() -> None:
    """Relative image paths are resolved to absolute raw.githubusercontent.com URLs."""
    md = "![screenshot](./screenshot.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert "https://raw.githubusercontent.com/owner/repo/main/screenshot.png" in result


def test_make_markdown_images_absolute_subdir_path() -> None:
    """Subdirectory-relative paths are resolved correctly."""
    md = "![img](docs/img.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert "https://raw.githubusercontent.com/owner/repo/main/docs/img.png" in result


def test_make_markdown_images_absolute_http_unchanged() -> None:
    """Absolute http:// image URLs are left unchanged."""
    md = "![img](https://example.com/img.png)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


def test_make_markdown_images_absolute_data_uri_unchanged() -> None:
    """Data URIs are left unchanged."""
    md = "![img](data:image/png;base64,abc)"
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


def test_make_markdown_images_absolute_no_images_noop() -> None:
    """Markdown with no images is returned unchanged."""
    md = "# Hello\n\nSome text without images."
    result = _make_markdown_images_absolute(md, _RAW_BASE)
    assert result == md


# ---------------------------------------------------------------------------
# fetch_github_readme tests
# ---------------------------------------------------------------------------


def _make_fake_requests_get(repo_data: dict, readme_data: dict | None = None) -> object:
    """Return a mock for ``requests.get`` that returns canned API responses."""

    class _FakeResp:
        def __init__(self, data: dict) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._data

    def _side_effect(url: str, **_kwargs: object) -> _FakeResp:
        if "readme" in url:
            return _FakeResp(readme_data or {})
        return _FakeResp(repo_data)

    return unittest.mock.patch("lobstergram.content.requests.get", side_effect=_side_effect)


def test_fetch_github_readme_returns_title_and_markdown() -> None:
    """fetch_github_readme returns (title, markdown) for a repo root URL."""
    readme_md = "# Installation\n\n```\npip install mylib\n```\n"
    repo_data = {
        "full_name": "owner/repo",
        "description": "A cool library",
    }
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode() + "\n",
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is not None
    title, markdown = result
    assert "owner/repo" in title
    assert "A cool library" in title
    assert "# Installation" in markdown
    assert "pip install mylib" in markdown


def test_fetch_github_readme_resolves_relative_images() -> None:
    """Relative image URLs in the README are resolved to absolute raw.githubusercontent.com URLs."""
    readme_md = "![screenshot](./docs/screenshot.png)\n"
    repo_data = {"full_name": "owner/repo", "description": ""}
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode(),
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is not None
    _, markdown = result
    assert "https://raw.githubusercontent.com/owner/repo/main/docs/screenshot.png" in markdown


def test_fetch_github_readme_non_markdown_readme_returns_none() -> None:
    """fetch_github_readme returns None when the README is not a Markdown file."""
    repo_data = {"full_name": "owner/repo", "description": ""}
    readme_data = {
        "name": "README.rst",
        "content": base64.b64encode(b"RST content").decode(),
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.rst",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is None


def test_fetch_github_readme_non_github_url_returns_none() -> None:
    """fetch_github_readme returns None immediately for non-GitHub URLs."""
    result = fetch_github_readme("https://example.com/owner/repo")
    assert result is None


def test_fetch_github_readme_subpath_url_returns_none() -> None:
    """fetch_github_readme returns None for GitHub URLs with sub-paths."""
    result = fetch_github_readme("https://github.com/owner/repo/issues/1")
    assert result is None


def test_fetch_github_readme_api_failure_returns_none() -> None:
    """fetch_github_readme returns None when the README API request fails."""
    import requests as _requests

    repo_data = {"full_name": "owner/repo", "description": ""}

    class _FakeResp:
        def __init__(self, data: dict) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return self._data

    def _side_effect(url: str, **_kwargs: object) -> _FakeResp:
        if "readme" in url:
            raise _requests.RequestException("readme API error")
        return _FakeResp(repo_data)

    with unittest.mock.patch("lobstergram.content.requests.get", side_effect=_side_effect):
        result = fetch_github_readme("https://github.com/owner/repo")

    assert result is None


# ---------------------------------------------------------------------------
# _strip_badge_paragraphs tests
# ---------------------------------------------------------------------------


def test_strip_badge_paragraphs_removes_badge_only_paragraph() -> None:
    """A paragraph consisting entirely of badge images is removed."""
    md = (
        "# Title\n\n"
        "[![npm](https://img.shields.io/npm/v/pkg)](https://npmjs.com/pkg) "
        "[![discord](https://img.shields.io/discord/123)](https://discord.gg/xyz)\n\n"
        "This is the real description."
    )
    result = _strip_badge_paragraphs(md)
    assert "shields.io" not in result
    assert "# Title" in result
    assert "This is the real description." in result


def test_strip_badge_paragraphs_keeps_mixed_paragraph() -> None:
    """A paragraph containing badges AND text is kept in full."""
    md = "[![badge](https://img.shields.io/x)](https://example.com) Install with pip."
    result = _strip_badge_paragraphs(md)
    assert result == md


def test_strip_badge_paragraphs_noop_when_no_badges() -> None:
    """Markdown without any badge paragraphs is returned unchanged."""
    md = "# Hello\n\nSome text without badges."
    assert _strip_badge_paragraphs(md) == md


def test_strip_badge_paragraphs_multiple_badge_paragraphs_all_removed() -> None:
    """Multiple consecutive badge-only paragraphs are all removed."""
    md = (
        "[![b1](https://img.shields.io/b1)](https://example.com/b1)\n\n"
        "[![b2](https://img.shields.io/b2)](https://example.com/b2)\n\n"
        "Real content here."
    )
    result = _strip_badge_paragraphs(md)
    assert "shields.io" not in result
    assert "Real content here." in result


# ---------------------------------------------------------------------------
# markdown_to_text empty-link stripping tests
# ---------------------------------------------------------------------------


def test_markdown_to_text_strips_empty_link_residue() -> None:
    """Empty links [](url) left after badge image stripping are removed."""
    # [![alt](img)](link) after stripping the image part becomes [](link)
    md = "[](https://www.npmjs.com/package/pkg) [](https://discord.gg/xyz)"
    result = markdown_to_text(md)
    assert "npmjs.com" not in result
    assert "discord.gg" not in result
    assert result.strip() == ""


def test_markdown_to_text_badge_paragraph_becomes_empty() -> None:
    """A paragraph of badge images is reduced to empty text by markdown_to_text."""
    badges = (
        "[![npm](https://img.shields.io/npm/v/pkg)](https://npmjs.com/pkg) "
        "[![discord](https://img.shields.io/discord/123)](https://discord.gg/xyz)"
    )
    result = markdown_to_text(badges)
    assert result.strip() == ""


# ---------------------------------------------------------------------------
# extract_intro badge-skipping tests
# ---------------------------------------------------------------------------


def test_extract_intro_skips_badge_only_paragraph() -> None:
    """extract_intro skips paragraphs that consist entirely of badge links."""
    md = (
        "[![npm](https://img.shields.io/npm/v/pkg)](https://npmjs.com/pkg) "
        "[![discord](https://img.shields.io/discord/123)](https://discord.gg/xyz)\n\n"
        "This is a tiny, simple library that does useful things."
    )
    intro = extract_intro(md, "")
    assert "npmjs.com" not in intro
    assert "discord.gg" not in intro
    assert "tiny, simple library" in intro


# ---------------------------------------------------------------------------
# fetch_github_readme badge-stripping tests
# ---------------------------------------------------------------------------


def test_fetch_github_readme_strips_badge_paragraphs() -> None:
    """fetch_github_readme strips badge-only paragraphs from the README."""
    readme_md = (
        "# mylib\n\n"
        "[![npm](https://img.shields.io/npm/v/mylib)](https://npmjs.com/mylib) "
        "[![ci](https://img.shields.io/github/actions/workflow/status/owner/mylib/ci.yml)](https://github.com/owner/mylib/actions)\n\n"
        "mylib is a great library.\n"
    )
    repo_data = {"full_name": "owner/mylib", "description": "A great library"}
    readme_data = {
        "name": "README.md",
        "content": base64.b64encode(readme_md.encode()).decode(),
        "download_url": "https://raw.githubusercontent.com/owner/mylib/main/README.md",
    }
    with _make_fake_requests_get(repo_data, readme_data):
        result = fetch_github_readme("https://github.com/owner/mylib")

    assert result is not None
    _, markdown = result
    assert "shields.io" not in markdown
    assert "# mylib" in markdown
    assert "mylib is a great library." in markdown
