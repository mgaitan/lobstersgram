"""Markdown cleanup that belongs to Telegraph page creation."""

from __future__ import annotations

import re


def strip_leading_title_heading(markdown: str, title: str) -> str:
    """Remove a leading Markdown heading when it duplicates the page title."""
    stripped = markdown.lstrip("\n")
    match = re.match(r"^#{1,6}\s+(.*)\s*$", stripped, re.MULTILINE)
    if match and match.group(1).strip().lower() == title.strip().lower():
        return stripped[match.end() :].lstrip("\n")
    return markdown
