"""Tests for md_to_dom.py — Markdown → Telegraph DOM conversion."""

from __future__ import annotations

from md_to_dom import md_to_dom

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def text_content(nodes: list) -> str:  # type: ignore[type-arg]
    """Recursively extract all text strings from a DOM node list."""
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            parts.extend(text_content(node.get("children") or []))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Soft line-break spacing (the core bug that was fixed)
# ---------------------------------------------------------------------------


class TestSoftLineBreakSpacing:
    """Spaces must be preserved when markdownify wraps inline elements across lines.

    markdownify converts <a>…</a> / <strong> / <em> / <code> and may emit a
    soft newline between the element and the surrounding text.  The renderer
    used to filter those single-space strings out, producing "missingSSH"-style
    concatenation.
    """

    def test_space_preserved_after_link(self) -> None:
        """Soft line break after a link must produce a space node."""
        md = "This is [some link](http://example.com)\nand more text."
        result = md_to_dom(md)
        assert len(result) == 1
        children = result[0]["children"]
        # The space " " must appear between the link node and "and more text."
        assert " " in children
        # No run-together text
        assert "and more text." in children
        assert text_content(result) == "This is some link and more text."

    def test_space_preserved_before_link(self) -> None:
        """Soft line break before a link must produce a space node."""
        md = "Read more\n[here](http://example.com) for details."
        result = md_to_dom(md)
        assert text_content(result) == "Read more here for details."

    def test_space_preserved_after_bold(self) -> None:
        """Soft line break after bold text must produce a space node."""
        md = "Hello **world**\nfoo bar."
        result = md_to_dom(md)
        assert len(result) == 1
        children = result[0]["children"]
        assert " " in children
        assert text_content(result) == "Hello world foo bar."

    def test_space_preserved_after_emphasis(self) -> None:
        """Soft line break after italic text must produce a space node."""
        md = "An *important*\nconcept."
        result = md_to_dom(md)
        assert text_content(result) == "An important concept."

    def test_space_preserved_after_inline_code(self) -> None:
        """Soft line break after inline code must produce a space node."""
        md = "Run `git status`\nto check."
        result = md_to_dom(md)
        assert text_content(result) == "Run git status to check."

    def test_space_preserved_between_link_and_code(self) -> None:
        """Soft line break between a link and inline code must produce spaces."""
        md = "See [docs](http://example.com)\n`ssh -L`\nfor details."
        result = md_to_dom(md)
        assert text_content(result) == "See docs ssh -L for details."

    def test_no_duplicate_spaces(self) -> None:
        """When the original text already has a trailing/leading space, no double space."""
        # markdownify preserves explicit spaces in the text
        md = "Hello **world** foo bar."
        result = md_to_dom(md)
        full = text_content(result)
        assert "  " not in full
        assert full == "Hello world foo bar."


# ---------------------------------------------------------------------------
# Standard inline rendering (spaces already in the text)
# ---------------------------------------------------------------------------


class TestInlineRendering:
    def test_link_with_surrounding_text(self) -> None:
        md = "The [link text](http://example.com) is here."
        result = md_to_dom(md)
        assert result == [
            {
                "tag": "p",
                "children": [
                    "The ",
                    {"tag": "a", "attrs": {"href": "http://example.com"}, "children": ["link text"]},
                    " is here.",
                ],
            }
        ]

    def test_bold_text(self) -> None:
        md = "This is **bold** text."
        result = md_to_dom(md)
        assert text_content(result) == "This is bold text."
        assert result[0]["children"][1] == {"tag": "strong", "children": ["bold"]}

    def test_italic_text(self) -> None:
        md = "This is *italic* text."
        result = md_to_dom(md)
        assert text_content(result) == "This is italic text."
        assert result[0]["children"][1] == {"tag": "em", "children": ["italic"]}

    def test_inline_code(self) -> None:
        md = "Use `print()` to output."
        result = md_to_dom(md)
        assert text_content(result) == "Use print() to output."
        assert result[0]["children"][1] == {"tag": "code", "children": ["print()"]}

    def test_strikethrough(self) -> None:
        md = "This is ~~wrong~~ right."
        result = md_to_dom(md)
        assert text_content(result) == "This is wrong right."
        assert result[0]["children"][1] == {"tag": "del", "children": ["wrong"]}


# ---------------------------------------------------------------------------
# Block-level rendering
# ---------------------------------------------------------------------------


class TestBlockRendering:
    def test_heading_h1_maps_to_h3(self) -> None:
        md = "# Title"
        result = md_to_dom(md)
        assert result == [{"tag": "h3", "children": ["Title"]}]

    def test_heading_h2_maps_to_h4(self) -> None:
        md = "## Subtitle"
        result = md_to_dom(md)
        assert result == [{"tag": "h4", "children": ["Subtitle"]}]

    def test_heading_h3_maps_to_strong_paragraph(self) -> None:
        md = "### Section"
        result = md_to_dom(md)
        assert result == [{"tag": "p", "children": [{"tag": "strong", "children": ["Section"]}]}]

    def test_unordered_list(self) -> None:
        md = "- item one\n- item two"
        result = md_to_dom(md)
        assert len(result) == 1
        assert result[0]["tag"] == "ul"
        assert len(result[0]["children"]) == 2  # noqa: PLR2004

    def test_ordered_list(self) -> None:
        md = "1. first\n2. second"
        result = md_to_dom(md)
        assert result[0]["tag"] == "ol"

    def test_blockquote(self) -> None:
        md = "> A quote"
        result = md_to_dom(md)
        assert result[0]["tag"] == "blockquote"

    def test_thematic_break(self) -> None:
        md = "---"
        result = md_to_dom(md)
        assert result == [{"tag": "hr"}]

    def test_block_code(self) -> None:
        md = "```python\nprint('hi')\n```"
        result = md_to_dom(md)
        assert result[0]["tag"] == "pre"

    def test_multiple_paragraphs(self) -> None:
        md = "First paragraph.\n\nSecond paragraph."
        result = md_to_dom(md)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0] == {"tag": "p", "children": ["First paragraph."]}
        assert result[1] == {"tag": "p", "children": ["Second paragraph."]}

    def test_hard_line_break_produces_br(self) -> None:
        md = "Line one  \nLine two"  # two trailing spaces → hard break
        result = md_to_dom(md)
        assert {"tag": "br"} in result[0]["children"]


# ---------------------------------------------------------------------------
# Empty / whitespace-only content
# ---------------------------------------------------------------------------


class TestEmptyContent:
    def test_empty_document(self) -> None:
        assert md_to_dom("") == []

    def test_whitespace_only_document(self) -> None:
        assert md_to_dom("   \n  \n  ") == []

    def test_empty_paragraph_is_skipped(self) -> None:
        """A paragraph that renders to nothing should be omitted from the output."""
        md = "Real content.\n\n\n\nMore content."
        result = md_to_dom(md)
        assert all(r.get("children") for r in result)


# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------


class TestImageRendering:
    def test_image_tag(self) -> None:
        md = "![alt text](http://example.com/img.png)"
        result = md_to_dom(md)
        assert result[0]["children"][0] == {
            "tag": "img",
            "attrs": {"src": "http://example.com/img.png", "alt": ["alt text"]},
        }
