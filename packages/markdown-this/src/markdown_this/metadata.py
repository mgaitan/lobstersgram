"""YAML front matter and HTML metadata helpers."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup

METADATA_FIELDS = ("title", "author", "url", "date", "image")


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


def add_front_matter(markdown: str, metadata: Mapping[str, str]) -> str:
    """Prepend non-empty metadata fields as YAML front matter."""
    fields = {field: metadata[field] for field in METADATA_FIELDS if metadata.get(field)}
    if not fields:
        return markdown
    header = yaml.safe_dump(fields, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n\n{markdown}" if markdown else f"---\n{header}\n---"


def extract_html_metadata(content_html: str, base_url: str = "") -> dict[str, str]:
    """Extract common author, canonical URL, date, and primary image metadata."""
    soup = BeautifulSoup(content_html, "html.parser")

    def first_meta(*queries: dict[str, str]) -> str:
        for query in queries:
            tag = soup.find("meta", attrs=query)
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    author = first_meta(
        {"name": "author"},
        {"property": "article:author"},
        {"name": "byline"},
        {"itemprop": "author"},
    )
    date = first_meta(
        {"property": "article:published_time"},
        {"name": "date"},
        {"itemprop": "datePublished"},
    )
    image = first_meta(
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
        {"itemprop": "image"},
    )
    image = urljoin(base_url, image) if image else ""
    parsed_image = urlparse(image)
    if parsed_image.scheme not in {"http", "https"} or not parsed_image.netloc:
        image = ""
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    url = str(canonical.get("href", "")).strip() if canonical else ""
    url = url or first_meta({"property": "og:url"})
    if not date:
        time_tag = soup.find("time", attrs={"datetime": True})
        date = str(time_tag["datetime"]).strip() if time_tag else ""
    return {
        field: value for field, value in (("author", author), ("url", url), ("date", date), ("image", image)) if value
    }
