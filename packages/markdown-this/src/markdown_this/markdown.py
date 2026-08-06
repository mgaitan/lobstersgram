"""Markdown cleanup and text extraction helpers."""

from __future__ import annotations

import re
import urllib.parse
from logging import getLogger

from bs4 import BeautifulSoup
from bs4.element import Tag

logger = getLogger(__name__)

_BADGE_RE = re.compile(r"\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)")
_HTML_P_BLOCK_RE = re.compile(r"<p(?:\s[^>]*)?>.*?</p>", re.IGNORECASE | re.DOTALL)
_BROKEN_LINK_RE = re.compile(r"\[(\s*\n[ \t]*\n[ \t]*)([^\]]*)\]\(")
_HARD_BREAK_BEFORE_LINK_RE = re.compile(r"(?<!\\) {2,}\n(?=\[[^\]]+\]\([^)]+\))")


def _extract_leading_heading(markdown: str) -> tuple[str | None, str]:
    """Extract and remove the first heading when it starts the Markdown."""
    stripped = markdown.lstrip("\n")
    match = re.match(r"^#{1,6}\s+(.*?)\s*$", stripped, re.MULTILINE)
    if match:
        return match.group(1).strip(), stripped[match.end() :].lstrip("\n")
    return None, markdown


def _is_html_badge_block(html: str) -> bool:  # noqa: C901
    """Return True if *html* is a ``<p>`` element containing at least two badge images."""
    soup = BeautifulSoup(html, "html.parser")
    p = soup.find("p")
    if p is None:
        return False
    img_count = 0
    for child in p.children:
        match child:
            case str() as text:
                if text.strip():
                    return False
            case Tag(name="img"):
                img_count += 1
            case Tag(name="a"):
                for grandchild in child.children:
                    match grandchild:
                        case str() as text:
                            if text.strip():
                                return False
                        case Tag(name="img"):
                            img_count += 1
                        case _:
                            return False
            case _:
                return False
    return img_count >= 2  # noqa: PLR2004


def _strip_badge_paragraphs(markdown: str) -> str:
    """Remove badge-only paragraphs from Markdown."""
    markdown = _HTML_P_BLOCK_RE.sub(
        lambda match: "" if _is_html_badge_block(match.group(0)) else match.group(0),
        markdown,
    )
    result: list[str] = []
    for paragraph in markdown.split("\n\n"):
        remaining = _BADGE_RE.sub("", paragraph).strip()
        if remaining:
            result.append(paragraph)
    return "\n\n".join(result)


def _make_markdown_images_absolute(markdown: str, base_url: str) -> str:
    """Resolve relative image URLs in Markdown against *base_url*."""

    def replace(match: re.Match[str]) -> str:
        alt, image_url = match.group(1), match.group(2)
        if image_url.startswith(("http://", "https://", "data:")):
            return match.group(0)
        return f"![{alt}]({urllib.parse.urljoin(base_url, image_url)})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, markdown)


def _make_markdown_links_absolute(markdown: str, base_url: str) -> str:
    """Resolve relative Markdown link URLs against *base_url*."""

    def replace(match: re.Match[str]) -> str:
        text, href = match.group(1), match.group(2).strip()
        if href.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
            return match.group(0)
        absolute = urllib.parse.urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            return match.group(0)
        return f"[{text}]({absolute})"

    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", replace, markdown)


def _normalize_markdown_links(markdown: str) -> str:
    """Fix Markdown links broken by blank lines or hard breaks."""

    def fix(match: re.Match[str]) -> str:
        text = match.group(2).replace("\n", " ").strip()
        return f"[{text}]("

    normalized = _BROKEN_LINK_RE.sub(fix, markdown)
    return _HARD_BREAK_BEFORE_LINK_RE.sub("\n", normalized)


def markdown_to_text(markdown_text: str) -> str:
    """Reduce Markdown to plain text suitable for previews."""
    text = markdown_text
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[\]\([^)]+\)", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"[_*]{1,3}([^_*]+)[_*]{1,3}", r"\1", text)


def extract_intro(markdown_text: str, fallback_text: str, min_length: int = 40) -> str:
    """Return the first substantial paragraph, falling back to plain text."""
    text = markdown_to_text(markdown_text)
    for chunk in text.split("\n\n"):
        line = chunk.strip()
        if not line:
            continue
        intro = line.replace("\n", " ").strip()
        if len(intro) >= min_length:
            return intro
    for line in fallback_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
