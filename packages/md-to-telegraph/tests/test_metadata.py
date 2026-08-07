"""Tests for reading YAML front matter."""

from md_to_telegraph import split_front_matter


def test_split_front_matter_reads_supported_fields() -> None:
    metadata, body = split_front_matter(
        "---\ntitle: Title\nauthor: Author\nurl: https://example.com\ndate: 2026-08-06\nimage: https://example.com/image.jpg\n---\n\nBody"
    )
    assert metadata == {
        "title": "Title",
        "author": "Author",
        "url": "https://example.com",
        "date": "2026-08-06",
        "image": "https://example.com/image.jpg",
    }
    assert body == "Body"


def test_split_front_matter_reads_page_type() -> None:
    metadata, body = split_front_matter("---\ntype: website\n---\n\nBody")

    assert metadata == {"type": "website"}
    assert body == "Body"


def test_split_front_matter_returns_original_without_valid_header() -> None:
    markdown = "Body"
    assert split_front_matter(markdown) == ({}, markdown)
    assert split_front_matter("---\ntitle: Title") == ({}, "---\ntitle: Title")
    invalid = "---\n- one\n---\n\nBody"
    assert split_front_matter(invalid) == ({}, invalid)
    invalid_yaml = "---\ntitle: [invalid\n---\n\nBody"
    assert split_front_matter(invalid_yaml) == ({}, invalid_yaml)
