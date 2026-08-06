"""Tests for extracting content from multiple source types."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

from markdown_this import extract_main_content
from markdown_this import extractor as extractor_module


def _document() -> unittest.mock.Mock:
    return unittest.mock.Mock(
        summary=unittest.mock.Mock(return_value="<article><p>Readable body.</p></article>"),
        title=unittest.mock.Mock(return_value="Readable title"),
    )


def test_extract_main_content_accepts_path_object(tmp_path: Path) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Source</body></html>", encoding="utf-8")
    with unittest.mock.patch.object(extractor_module, "Document", return_value=_document()):
        title, markdown, fallback_text, intro = extract_main_content(html_path, min_content_length=0)

    assert title == "Readable title"
    assert markdown == "Readable body."
    assert fallback_text == "Readable body."
    assert intro == "Readable body."


def test_extract_main_content_accepts_path_string(tmp_path: Path) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Source</body></html>", encoding="utf-8")
    with unittest.mock.patch.object(extractor_module, "Document", return_value=_document()):
        result = extract_main_content(str(html_path), min_content_length=0)

    assert result[0] == "Readable title"


def test_extract_main_content_accepts_raw_html() -> None:
    with unittest.mock.patch.object(extractor_module, "Document", return_value=_document()):
        result = extract_main_content("<html><body>Raw HTML</body></html>", min_content_length=0)

    assert result[:2] == ("Readable title", "Readable body.")

