"""Tests for md_to_telegraph — Markdown → Telegraph DOM conversion."""

from __future__ import annotations

from md_to_telegraph import md_to_telegraph

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


def test_soft_break_space_preserved_after_link() -> None:
    """Soft line break after a link must produce a space node."""
    md = "This is [some link](http://example.com)\nand more text."
    result = md_to_telegraph(md)
    assert len(result) == 1
    children = result[0]["children"]
    assert " " in children
    assert "and more text." in children
    assert text_content(result) == "This is some link and more text."


def test_soft_break_space_preserved_before_link() -> None:
    """Soft line break before a link must produce a space node."""
    md = "Read more\n[here](http://example.com) for details."
    result = md_to_telegraph(md)
    assert text_content(result) == "Read more here for details."


def test_soft_break_space_preserved_after_bold() -> None:
    """Soft line break after bold text must produce a space node."""
    md = "Hello **world**\nfoo bar."
    result = md_to_telegraph(md)
    assert len(result) == 1
    children = result[0]["children"]
    assert " " in children
    assert text_content(result) == "Hello world foo bar."


def test_soft_break_space_preserved_after_emphasis() -> None:
    """Soft line break after italic text must produce a space node."""
    md = "An *important*\nconcept."
    result = md_to_telegraph(md)
    assert text_content(result) == "An important concept."


def test_soft_break_space_preserved_after_inline_code() -> None:
    """Soft line break after inline code must produce a space node."""
    md = "Run `git status`\nto check."
    result = md_to_telegraph(md)
    assert text_content(result) == "Run git status to check."


def test_soft_break_space_preserved_between_link_and_code() -> None:
    """Soft line break between a link and inline code must produce spaces."""
    md = "See [docs](http://example.com)\n`ssh -L`\nfor details."
    result = md_to_telegraph(md)
    assert text_content(result) == "See docs ssh -L for details."


def test_soft_break_no_duplicate_spaces() -> None:
    """When the original text already has a space, no double space."""
    md = "Hello **world** foo bar."
    result = md_to_telegraph(md)
    full = text_content(result)
    assert "  " not in full
    assert full == "Hello world foo bar."


def test_soft_break_hiding_ssh_case() -> None:
    """Regression: 'hidingSSH' concatenation from bofh.it-style articles.

    readability+markdownify can emit newlines around inline code instead of
    spaces (e.g. 'hiding\\n`SSH`\\nin HTTPS').  render_inner used to filter
    out the ' ' produced by render_line_break for soft breaks, joining words
    without a separator.
    """
    md = "hiding\n`SSH`\nin HTTPS"
    result = md_to_telegraph(md)
    children = result[0]["children"]
    assert " " in children
    assert text_content(result) == "hiding SSH in HTTPS"


def test_soft_break_inline_code_at_start_of_line() -> None:
    """Soft line break before inline code at the start of a line."""
    md = "`SSH`\ntraffic hiding"
    result = md_to_telegraph(md)
    assert text_content(result) == "SSH traffic hiding"
    children = result[0]["children"]
    assert " " in children


# ---------------------------------------------------------------------------
# Inline rendering (spaces already present in the source text)
# ---------------------------------------------------------------------------


def test_inline_link_with_surrounding_text() -> None:
    md = "The [link text](http://example.com) is here."
    result = md_to_telegraph(md)
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


def test_inline_bold_text() -> None:
    md = "This is **bold** text."
    result = md_to_telegraph(md)
    assert text_content(result) == "This is bold text."
    assert result[0]["children"][1] == {"tag": "strong", "children": ["bold"]}


def test_inline_italic_text() -> None:
    md = "This is *italic* text."
    result = md_to_telegraph(md)
    assert text_content(result) == "This is italic text."
    assert result[0]["children"][1] == {"tag": "em", "children": ["italic"]}


def test_inline_code() -> None:
    md = "Use `print()` to output."
    result = md_to_telegraph(md)
    assert text_content(result) == "Use print() to output."
    assert result[0]["children"][1] == {"tag": "code", "children": ["print()"]}


def test_inline_strikethrough() -> None:
    md = "This is ~~wrong~~ right."
    result = md_to_telegraph(md)
    assert text_content(result) == "This is wrong right."
    assert result[0]["children"][1] == {"tag": "del", "children": ["wrong"]}


def test_inline_autolink() -> None:
    md = "<https://example.com>"
    result = md_to_telegraph(md)
    link = result[0]["children"][0]
    assert link == {"tag": "a", "attrs": {"href": "https://example.com"}, "children": ["https://example.com"]}


def test_inline_link_with_title() -> None:
    md = '[text](http://example.com "My title")'
    result = md_to_telegraph(md)
    link = result[0]["children"][0]
    assert link["tag"] == "a"
    assert link["attrs"]["title"] == "My title"
    assert link["attrs"]["href"] == "http://example.com"


def test_inline_bold_inside_link() -> None:
    """Nested inline: bold text inside a link."""
    md = "[**bold**](http://example.com)"
    result = md_to_telegraph(md)
    link = result[0]["children"][0]
    assert link["tag"] == "a"
    assert link["children"] == [{"tag": "strong", "children": ["bold"]}]


def test_inline_code_inside_link() -> None:
    """Nested inline: inline code inside a link."""
    md = "[`code`](http://example.com)"
    result = md_to_telegraph(md)
    link = result[0]["children"][0]
    assert link["tag"] == "a"
    assert link["children"] == [{"tag": "code", "children": ["code"]}]


def test_inline_html_span_text_preserved() -> None:
    """Raw HTML spans keep their text content without leaking HTML tags."""
    md = "<b>raw html</b>"
    result = md_to_telegraph(md)
    full = text_content(result)
    assert full == "raw html"


# ---------------------------------------------------------------------------
# Block-level rendering
# ---------------------------------------------------------------------------


def test_block_heading_h1_maps_to_h3() -> None:
    md = "# Title"
    result = md_to_telegraph(md)
    assert result == [{"tag": "h3", "children": ["Title"]}]


def test_block_heading_h2_maps_to_h4() -> None:
    md = "## Subtitle"
    result = md_to_telegraph(md)
    assert result == [{"tag": "h4", "children": ["Subtitle"]}]


def test_block_heading_h3_maps_to_strong_paragraph() -> None:
    md = "### Section"
    result = md_to_telegraph(md)
    assert result == [{"tag": "p", "children": [{"tag": "strong", "children": ["Section"]}]}]


def test_block_heading_h4_and_deeper_map_to_strong_paragraph() -> None:
    """h4 and deeper headings are also rendered as strong paragraphs."""
    for prefix in ("#### ", "##### ", "###### "):
        result = md_to_telegraph(f"{prefix}Deep heading")
        assert result[0] == {"tag": "p", "children": [{"tag": "strong", "children": ["Deep heading"]}]}


def test_block_unordered_list() -> None:
    md = "- item one\n- item two"
    result = md_to_telegraph(md)
    assert len(result) == 1
    assert result[0]["tag"] == "ul"
    assert len(result[0]["children"]) == 2  # noqa: PLR2004


def test_block_ordered_list() -> None:
    md = "1. first\n2. second"
    result = md_to_telegraph(md)
    assert result[0]["tag"] == "ol"


def test_block_nested_list() -> None:
    """A list item may contain a nested sub-list."""
    md = "- outer\n    - inner"
    result = md_to_telegraph(md)
    outer_item = result[0]["children"][0]
    nested_tags = [c["tag"] for c in outer_item["children"] if isinstance(c, dict)]
    assert "ul" in nested_tags


def test_block_list_item_with_inline_elements() -> None:
    """List items may contain inline markup."""
    md = "- item with **bold** text"
    result = md_to_telegraph(md)
    full = text_content(result)
    assert full == "item with bold text"


def test_block_blockquote() -> None:
    md = "> A quote"
    result = md_to_telegraph(md)
    assert result[0]["tag"] == "blockquote"


def test_block_blockquote_with_link() -> None:
    """Blockquotes may contain inline elements like links."""
    md = "> A [linked](http://example.com) quote"
    result = md_to_telegraph(md)
    assert result[0]["tag"] == "blockquote"
    assert text_content(result) == "A linked quote"


def test_block_thematic_break() -> None:
    md = "---"
    result = md_to_telegraph(md)
    assert result == [{"tag": "hr"}]


def test_block_code() -> None:
    md = "```python\nprint('hi')\n```"
    result = md_to_telegraph(md)
    assert result[0]["tag"] == "pre"


def test_block_code_language_class() -> None:
    """Code block with a language hint gets the appropriate CSS class."""
    md = "```python\nprint()\n```"
    result = md_to_telegraph(md)
    code_node = result[0]["children"][0]
    assert code_node["tag"] == "code"
    assert code_node["attrs"]["class"] == "language-python"


def test_block_code_no_language() -> None:
    """Code block without language hint has no attrs."""
    md = "```\nplain code\n```"
    result = md_to_telegraph(md)
    code_node = result[0]["children"][0]
    assert code_node["tag"] == "code"
    assert "attrs" not in code_node


def test_block_code_multiline_has_br_nodes() -> None:
    """Multi-line code blocks use <br> to separate lines."""
    md = "```\nline1\nline2\nline3\n```"
    result = md_to_telegraph(md)
    code_children = result[0]["children"][0]["children"]
    assert code_children[0] == "line1"
    assert code_children[1] == {"tag": "br"}
    assert code_children[2] == "line2"


def test_block_multiple_paragraphs() -> None:
    md = "First paragraph.\n\nSecond paragraph."
    result = md_to_telegraph(md)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0] == {"tag": "p", "children": ["First paragraph."]}
    assert result[1] == {"tag": "p", "children": ["Second paragraph."]}


def test_block_hard_line_break_produces_br() -> None:
    md = "Line one  \nLine two"  # two trailing spaces → hard break
    result = md_to_telegraph(md)
    assert {"tag": "br"} in result[0]["children"]


# ---------------------------------------------------------------------------
# Empty / whitespace-only content
# ---------------------------------------------------------------------------


def test_empty_document() -> None:
    assert md_to_telegraph("") == []


def test_whitespace_only_document() -> None:
    assert md_to_telegraph("   \n  \n  ") == []


def test_nbsp_only_paragraph_is_skipped() -> None:
    """A paragraph containing only &nbsp; (non-breaking space) is treated as empty."""
    assert md_to_telegraph("&nbsp;") == []


def test_nbsp_only_paragraph_in_blockquote_is_skipped() -> None:
    """A blockquote whose only content is an &nbsp; paragraph gets empty children."""
    result = md_to_telegraph("> &nbsp;")
    assert result == [{"tag": "blockquote", "children": []}]


# ---------------------------------------------------------------------------
# Raw HTML sanitizing
# ---------------------------------------------------------------------------


def test_html_block_text_preserved_without_raw_tags() -> None:
    """An HTML block is converted into Telegraph paragraphs with plain text."""
    md = "<pre>\ncode here\n</pre>"
    result = md_to_telegraph(md)
    assert len(result) == 1
    assert result[0] == {"tag": "p", "children": ["code here"]}


def test_html_span_text_preserved_without_raw_tags() -> None:
    """Inline HTML tags within a paragraph keep only their text content."""
    md = "text <em>emphasis</em> end"
    result = md_to_telegraph(md)
    full = text_content(result)
    assert full == "text emphasis end"
    children = result[0]["children"]
    assert all("<em>" not in c for c in children if isinstance(c, str))


def test_html_block_multiple_paragraphs_are_split() -> None:
    """Block HTML with multiple paragraphs becomes multiple Telegraph nodes."""
    md = "<div><p>first</p><p>second</p></div>"
    result = md_to_telegraph(md)
    assert result == [
        {"tag": "p", "children": ["first"]},
        {"tag": "p", "children": ["second"]},
    ]


def test_empty_html_block_is_skipped() -> None:
    """HTML blocks with no visible text do not create empty Telegraph nodes."""
    assert md_to_telegraph("<div></div>") == []


def test_html_block_inside_blockquote_is_flattened() -> None:
    """Nested HTML blocks inside containers are flattened into child nodes."""
    md = "> <div><p>first</p><p>second</p></div>"
    result = md_to_telegraph(md)
    assert result == [
        {
            "tag": "blockquote",
            "children": [
                {"tag": "p", "children": ["first"]},
                {"tag": "p", "children": ["second"]},
            ],
        }
    ]


# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------


def test_image_tag() -> None:
    md = "![alt text](http://example.com/img.png)"
    result = md_to_telegraph(md)
    assert result[0]["children"][0] == {
        "tag": "img",
        "attrs": {"src": "http://example.com/img.png", "alt": "alt text"},
    }


def test_image_with_title() -> None:
    md = '![alt](http://example.com/img.png "Caption")'
    result = md_to_telegraph(md)
    img = result[0]["children"][0]
    assert img["tag"] == "img"
    assert img["attrs"]["src"] == "http://example.com/img.png"
    assert img["attrs"]["alt"] == "alt"
    assert img["attrs"]["title"] == "Caption"


def test_image_alt_text_with_inline_markup_is_flattened() -> None:
    md = "![**bold** and *em*](http://example.com/img.png)"
    result = md_to_telegraph(md)
    img = result[0]["children"][0]
    assert img["attrs"]["alt"] == "bold and em"


def test_image_no_alt_text() -> None:
    md = "![](http://example.com/img.png)"
    result = md_to_telegraph(md)
    img = result[0]["children"][0]
    assert img["tag"] == "img"
    assert img["attrs"]["src"] == "http://example.com/img.png"
    assert not img["attrs"].get("alt")
