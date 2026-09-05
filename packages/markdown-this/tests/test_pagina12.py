"""Tests for Pagina/12 Fusion.globalContent extraction."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import requests
from markdown_this import fetch_pagina12_article, split_front_matter
from markdown_this import fetchers as fetchers_module

URL = "https://www.pagina12.com.ar/2026/09/03/el-oficialismo-continua-con-su-desprecio-a-los-necesitados/"
FIXTURE = Path(__file__).parent / "fixtures" / "extraction" / "pagina12_fusion_article.html"


def test_fetch_pagina12_article_extracts_fusion_content_and_metadata() -> None:
    with unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=FIXTURE.read_text(encoding="utf-8")):
        result = fetch_pagina12_article(URL)

    assert result is not None
    title, markdown = result
    metadata, body = split_front_matter(markdown)
    assert title == "El oficialismo continua con su desprecio a los necesitados"
    assert metadata == {
        "author": "Pagina/12",
        "url": URL,
        "date": "2026-09-03T12:00:00Z",
        "image": "https://images.pagina12.com.ar/styles/focal_3_2_960x640/public/2026-09/hero.jpg",
    }
    assert "El proyecto oficial volvio a quedar lejos de las demandas sociales." in body
    assert "La oposicion cuestiono el recorte durante la sesion." in body
    assert "Copiar enlace" not in body
    assert "Ultimas noticias" not in body


def test_fetch_pagina12_article_rejects_other_domains_and_fetch_failures() -> None:
    assert fetch_pagina12_article("https://example.com/article") is None

    with unittest.mock.patch(
        "markdown_this.fetchers.fetch_html",
        side_effect=requests.RequestException("network error"),
    ):
        assert fetch_pagina12_article(URL) is None

    with unittest.mock.patch("markdown_this.fetchers.fetch_html", return_value=""):
        assert fetch_pagina12_article(URL) is None


def test_parse_pagina12_html_handles_missing_or_unusable_fusion_data() -> None:
    assert fetchers_module._parse_pagina12_html("<html></html>", URL) is None
    assert fetchers_module._parse_pagina12_html("<script>Fusion.globalContent = {};</script>", URL) is None
    assert (
        fetchers_module._parse_pagina12_html(
            '<script>Fusion.globalContent = {"content_elements":[{"type":"raw_html"}]};</script>', URL
        )
        is None
    )


def test_extract_balanced_js_object_handles_invalid_shapes() -> None:
    assert fetchers_module._extract_balanced_js_object("no marker", "Fusion.globalContent") is None
    assert fetchers_module._extract_balanced_js_object("Fusion.globalContent = null;", "Fusion.globalContent") is None
    assert (
        fetchers_module._extract_balanced_js_object("Fusion.globalContent = {'bad': true};", "Fusion.globalContent")
        is None
    )
    assert (
        fetchers_module._extract_balanced_js_object(
            'Fusion.globalContent = {"title": "unterminated"', "Fusion.globalContent"
        )
        is None
    )
    assert fetchers_module._extract_balanced_js_object(
        'Fusion.globalContent = {"title": "An \\"escaped\\" title"};',
        "Fusion.globalContent",
    ) == {"title": 'An "escaped" title'}


def test_fusion_element_markdown_handles_supported_and_ignored_elements() -> None:
    assert fetchers_module._fusion_element_markdown({"type": "text", "content": "<strong>Body</strong>"}, URL) == (
        "**Body**"
    )
    assert fetchers_module._fusion_element_markdown({"type": "header", "level": 3, "content": "Section"}, URL) == (
        "### Section"
    )
    assert (
        fetchers_module._fusion_element_markdown(
            {
                "type": "image",
                "url": "/images/photo.jpg",
                "alt_text": "<b>Hero</b>",
                "caption": "Photo caption",
            },
            URL,
        )
        == "![Hero](https://www.pagina12.com.ar/images/photo.jpg)\n\nPhoto caption"
    )
    assert fetchers_module._fusion_element_markdown({"type": "image", "url": "data:image/png;base64,abc"}, URL) == ""
    assert fetchers_module._fusion_element_markdown({"type": "unknown"}, URL) == ""
