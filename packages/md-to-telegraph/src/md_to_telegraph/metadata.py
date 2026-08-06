"""YAML front matter helpers for Markdown page inputs."""

from __future__ import annotations

from collections.abc import Mapping

import yaml

METADATA_FIELDS = ("title", "author", "url", "date")


def split_front_matter(markdown: str) -> tuple[dict[str, str], str]:
    """Return front matter metadata and the Markdown body."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown

    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, markdown

    try:
        loaded = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return {}, markdown
    if not isinstance(loaded, Mapping):
        return {}, markdown
    metadata = {
        field: str(value)
        for field in METADATA_FIELDS
        if (value := loaded.get(field)) is not None and not isinstance(value, (dict, list))
    }
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return metadata, body
