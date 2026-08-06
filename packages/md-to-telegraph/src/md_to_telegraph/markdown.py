"""Markdown cleanup that belongs to Telegraph page creation."""

from __future__ import annotations

import re


def extract_leading_title(markdown: str) -> str:
    """Return the first ATX heading title, or an empty string."""
    lines = markdown.splitlines()
    first_line = lines[0] if lines else ""
    match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", first_line)
    return match.group(1).strip() if match else ""


def strip_leading_title_heading(markdown: str, title: str) -> str:
    """Remove a leading Markdown heading when it duplicates the page title."""
    stripped = markdown.lstrip("\n")
    match = re.match(r"^#{1,6}\s+(.*)\s*$", stripped, re.MULTILINE)
    if match and match.group(1).strip().lower() == title.strip().lower():
        return stripped[match.end() :].lstrip("\n")
    return markdown
