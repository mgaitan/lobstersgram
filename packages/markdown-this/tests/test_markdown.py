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
    strip_leading_title_heading,
)
from markdown_this import extractor as extractor_module
from markdown_this import html as html_module
from markdown_this import markdown as markdown_module

BASE = "https://example.com/articles/my-post/"

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
# _is_html_badge_block tests
# ---------------------------------------------------------------------------


def test_is_html_badge_block_single_linked_image() -> None:
    """A <p> with only one <a><img></a> is NOT a badge block (logo/hero image)."""
    html = (
        '<p align="center"><a href="https://example.com">'
        '<img src="https://img.shields.io/badge/x-blue.svg" alt="x"/></a></p>'
    )
    assert _is_html_badge_block(html) is False


def test_is_html_badge_block_multiple_linked_images() -> None:
    """A <p> with multiple <a><img></a> patterns is a badge block."""
    html = (
        '<p align="center">'
        '<a href="https://example.com/a"><img src="https://img.shields.io/a.svg" alt="a"/></a>'
        ' <a href="https://example.com/b"><img src="https://img.shields.io/b.svg" alt="b"/></a>'
        "</p>"
    )
    assert _is_html_badge_block(html) is True


def test_is_html_badge_block_standalone_img() -> None:
    """A <p> with a single bare <img> is NOT a badge block (below 2-image minimum)."""
    html = '<p><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"/></p>'
    assert _is_html_badge_block(html) is False


def test_is_html_badge_block_two_standalone_imgs() -> None:
    """A <p> with two bare <img> elements meets the 2-image minimum."""
    html = (
        "<p>"
        '<img src="https://img.shields.io/badge/a-blue.svg" alt="a"/> '
        '<img src="https://img.shields.io/badge/b-green.svg" alt="b"/>'
        "</p>"
    )
    assert _is_html_badge_block(html) is True


def test_is_html_badge_block_with_text_is_not_badge() -> None:
    """A <p> that contains text alongside images is not a badge block."""
    html = '<p>Install with pip. <img src="https://img.shields.io/x.svg" alt="x"/></p>'
    assert _is_html_badge_block(html) is False


def test_is_html_badge_block_no_img_is_not_badge() -> None:
    """A <p> with only an <a> and no <img> is not a badge block."""
    html = '<p><a href="https://example.com">Click here</a></p>'
    assert _is_html_badge_block(html) is False


def test_is_html_badge_block_empty_p_is_not_badge() -> None:
    """An empty <p> (no <img>) is not considered a badge block."""
    html = "<p></p>"
    assert _is_html_badge_block(html) is False


def test_is_html_badge_block_non_p_tag_is_not_badge() -> None:
    """HTML that is not a <p> element is not a badge block."""
    html = '<div><img src="https://img.shields.io/x.svg"/></div>'
    assert _is_html_badge_block(html) is False


# ---------------------------------------------------------------------------
# _strip_badge_paragraphs - HTML badge block tests
# ---------------------------------------------------------------------------


def test_strip_badge_paragraphs_removes_html_badge_block() -> None:
    """A <p> block containing only <a><img></a> badge links is removed."""
    md = (
        "# llm.rb\n\n"
        '<p align="center">'
        '<a href="https://0x1eef.github.io/x/llm.rb">'
        '<img src="https://img.shields.io/badge/docs-blue.svg" alt="RubyDoc"/>'
        "</a>"
        ' <a href="https://opensource.org/license/0bsd">'
        '<img src="https://img.shields.io/badge/License-0BSD-orange.svg" alt="License"/>'
        "</a>"
        "</p>\n\n"
        "llm.rb is Ruby's most capable AI runtime."
    )
    result = _strip_badge_paragraphs(md)
    assert "shields.io" not in result
    assert "# llm.rb" in result
    assert "llm.rb is Ruby" in result


def test_strip_badge_paragraphs_removes_multiline_html_badge_block() -> None:
    """A multiline <p> badge block (common in GitHub READMEs) is removed."""
    md = (
        "# Title\n\n"
        '<p align="center">\n'
        '  <a href="https://example.com/a"><img src="https://img.shields.io/a.svg" alt="A"/></a>\n'
        '  <a href="https://example.com/b"><img src="https://img.shields.io/b.svg" alt="B"/></a>\n'
        "</p>\n\n"
        "Real description."
    )
    result = _strip_badge_paragraphs(md)
    assert "shields.io" not in result
    assert "# Title" in result
    assert "Real description." in result


def test_strip_badge_paragraphs_keeps_p_with_text() -> None:
    """A <p> block that contains text (not only images) is kept."""
    md = '<p>This is a description. <img src="https://img.shields.io/x.svg" alt="x"/></p>'
    result = _strip_badge_paragraphs(md)
    assert "This is a description." in result


def test_strip_badge_paragraphs_html_badges_not_separated_by_blank_lines() -> None:
    """Multiple consecutive HTML badge <p> blocks without blank lines are all removed."""
    md = (
        "# Title\n\n"
        '<p align="center">'
        '<a href="https://example.com/a"><img src="https://img.shields.io/a.svg" alt="A"/></a>'
        '<a href="https://example.com/b"><img src="https://img.shields.io/b.svg" alt="B"/></a>'
        "</p>"
        '<p align="center">'
        '<a href="https://example.com/c"><img src="https://img.shields.io/c.svg" alt="C"/></a>'
        '<a href="https://example.com/d"><img src="https://img.shields.io/d.svg" alt="D"/></a>'
        "</p>\n\n"
        "Real description."
    )
    result = _strip_badge_paragraphs(md)
    assert "shields.io" not in result
    assert "# Title" in result
    assert "Real description." in result


def test_strip_badge_paragraphs_keeps_single_img_p() -> None:
    """A <p> with a single <img> (e.g. a logo) is kept, not treated as badges."""
    md = (
        "# Title\n\n"
        '<p align="center"><a href="https://example.com">'
        '<img src="https://example.com/logo.png" alt="Logo"/></a></p>\n\n'
        "Real description."
    )
    result = _strip_badge_paragraphs(md)
    assert "logo.png" in result
    assert "Real description." in result


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
# _normalize_markdown_links tests
# ---------------------------------------------------------------------------


def test_normalize_markdown_links_converts_hard_break_before_inline_link() -> None:
    """Hard line breaks before sentence links are downgraded to soft breaks."""
    md = (
        "If you like these, you can follow the  \n"
        "[author](https://example.com/author), buy them a  \n"
        "[coffee](https://example.com/coffee), or  \n"
        "[suggest what comes next](https://example.com/next)"
    )
    normalized = _normalize_markdown_links(md)
    assert normalized == (
        "If you like these, you can follow the\n"
        "[author](https://example.com/author), buy them a\n"
        "[coffee](https://example.com/coffee), or\n"
        "[suggest what comes next](https://example.com/next)"
    )


# ---------------------------------------------------------------------------
# strip_leading_title_heading tests
# ---------------------------------------------------------------------------


def test_strip_leading_title_heading_exact_match() -> None:
    """The leading h1 heading is removed when it exactly matches the title."""
    md = "# My Article Title\n\nSome content here."
    result = strip_leading_title_heading(md, "My Article Title")
    assert result == "Some content here."
    assert "My Article Title" not in result


def test_strip_leading_title_heading_case_insensitive() -> None:
    """The comparison is case-insensitive."""
    md = "# the machines are fine. I'm worried about us.\n\nContent."
    result = strip_leading_title_heading(md, "The machines are fine. I'm worried about us.")
    assert "the machines are fine" not in result
    assert "Content." in result


def test_strip_leading_title_heading_no_match_kept() -> None:
    """The heading is kept when its text does not match the title."""
    md = "# Different Title\n\nContent."
    result = strip_leading_title_heading(md, "My Article")
    assert result == md


def test_strip_leading_title_heading_h2_removed() -> None:
    """Works for h2 headings as well."""
    md = "## Section Heading\n\nContent."
    result = strip_leading_title_heading(md, "Section Heading")
    assert "Section Heading" not in result
    assert "Content." in result


def test_strip_leading_title_heading_no_heading_unchanged() -> None:
    """Markdown without a leading heading is returned unchanged."""
    md = "Just a paragraph with no heading."
    result = strip_leading_title_heading(md, "Just a paragraph with no heading.")
    assert result == md


def test_strip_leading_title_heading_leading_blank_lines_ignored() -> None:
    """Leading blank lines before the heading are ignored."""
    md = "\n\n# My Title\n\nContent."
    result = strip_leading_title_heading(md, "My Title")
    assert "My Title" not in result
    assert "Content." in result


def test_strip_leading_title_heading_trailing_blank_lines_stripped() -> None:
    """Blank lines between the removed heading and content are stripped."""
    md = "# My Title\n\n\nContent paragraph."
    result = strip_leading_title_heading(md, "My Title")
    assert result == "Content paragraph."


# ---------------------------------------------------------------------------
# _extract_leading_heading tests
# ---------------------------------------------------------------------------


def test_extract_leading_heading_h1() -> None:
    """Extracts an h1 heading and returns the rest of the markdown."""
    md = "# Real Title\n\nSome body content."
    heading, rest = _extract_leading_heading(md)
    assert heading == "Real Title"
    assert rest == "Some body content."


def test_extract_leading_heading_h2() -> None:
    """Extracts an h2 heading (common in GitHub markdown files)."""
    md = "## Embedding EYG in Gleam programs\n\nEYG is type safe."
    heading, rest = _extract_leading_heading(md)
    assert heading == "Embedding EYG in Gleam programs"
    assert rest == "EYG is type safe."


def test_extract_leading_heading_no_heading_returns_none() -> None:
    """Returns (None, original_markdown) when no leading heading is present."""
    md = "Just a plain paragraph."
    heading, rest = _extract_leading_heading(md)
    assert heading is None
    assert rest == md


def test_extract_leading_heading_blank_lines_before_heading() -> None:
    """Leading blank lines before the heading are ignored."""
    md = "\n\n# Title Here\n\nBody."
    heading, rest = _extract_leading_heading(md)
    assert heading == "Title Here"
    assert rest == "Body."


def test_extract_leading_heading_strips_only_first_heading() -> None:
    """Only the very first heading is extracted; subsequent headings stay in rest."""
    md = "# First\n\n## Second\n\nContent."
    heading, rest = _extract_leading_heading(md)
    assert heading == "First"
    assert "## Second" in rest
    assert "Content." in rest


# ---------------------------------------------------------------------------
