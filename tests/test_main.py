"""Tests for main.py helpers."""

from __future__ import annotations

import os

# Provide required env vars before importing main (they are read at module level).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAPH_ACCESS_TOKEN", "test-token")

from main import make_images_absolute

BASE = "https://example.com/articles/my-post/"


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
