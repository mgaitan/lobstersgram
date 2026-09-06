"""Tests for extracting content from multiple source types."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

from markdown_this import extract_main_content, split_front_matter
from markdown_this import extractor as extractor_module
from pytest_mock import MockerFixture


def _document(*, mocker: MockerFixture) -> unittest.mock.Mock:
    return mocker.Mock(
        summary=mocker.Mock(return_value="<article><p>Readable body.</p></article>"),
        title=mocker.Mock(return_value="Readable title"),
    )


def test_extract_main_content_accepts_path_object(tmp_path: Path, *, mocker: MockerFixture) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Source</body></html>", encoding="utf-8")
    mocker.patch.object(extractor_module, "Document", return_value=_document(mocker=mocker))
    title, markdown, fallback_text, intro = extract_main_content(html_path, min_content_length=0)

    assert title == "Readable title"
    metadata, body = split_front_matter(markdown)
    assert metadata == {"title": "Readable title"}
    assert body == "Readable body."
    assert fallback_text == "Readable body."
    assert intro == "Readable body."


def test_extract_main_content_accepts_path_string(tmp_path: Path, *, mocker: MockerFixture) -> None:
    html_path = tmp_path / "article.html"
    html_path.write_text("<html><body>Source</body></html>", encoding="utf-8")
    mocker.patch.object(extractor_module, "Document", return_value=_document(mocker=mocker))
    result = extract_main_content(str(html_path), min_content_length=0)

    assert result[0] == "Readable title"


def test_extract_main_content_accepts_raw_html(*, mocker: MockerFixture) -> None:
    mocker.patch.object(extractor_module, "Document", return_value=_document(mocker=mocker))
    result = extract_main_content("<html><body>Raw HTML</body></html>", min_content_length=0)

    metadata, body = split_front_matter(result[1])
    assert result[0] == "Readable title"
    assert metadata == {"title": "Readable title"}
    assert body == "Readable body."


def test_extract_main_content_emits_html_metadata(*, mocker: MockerFixture) -> None:
    html = (
        '<meta name="author" content="Author">'
        '<link rel="canonical" href="https://example.com/article">'
        '<meta property="article:published_time" content="2026-08-06">'
        '<meta property="og:image" content="https://cdn.example.com/hero.jpg">'
        "<p>Raw HTML</p>"
    )
    mocker.patch.object(extractor_module, "Document", return_value=_document(mocker=mocker))
    result = extract_main_content(html, min_content_length=0)

    metadata, _body = split_front_matter(result[1])
    assert metadata == {
        "title": "Readable title",
        "author": "Author",
        "url": "https://example.com/article",
        "date": "2026-08-06",
        "image": "https://cdn.example.com/hero.jpg",
    }


def test_extract_main_content_falls_back_when_special_url_extractor_fails(*, mocker: MockerFixture) -> None:
    broken_extractor = mocker.Mock(side_effect=RuntimeError("broken"))
    ignored_extractor = mocker.Mock(return_value=None)
    html = "<html><body><article><p>Fallback body.</p></article></body></html>"
    mocker.patch.object(extractor_module, "SPECIAL_URL_EXTRACTORS", (broken_extractor, ignored_extractor))
    mocker.patch.object(extractor_module, "fetch_html", return_value=html)
    mocker.patch.object(extractor_module, "Document", return_value=_document(mocker=mocker))
    title, markdown, fallback_text, intro = extract_main_content("https://example.com/article", min_content_length=0)

    assert title == "Readable title"
    assert "Readable body." in markdown
    assert fallback_text == "Readable body."
    assert intro == "Readable body."


def test_extract_main_content_excludes_structural_ad_slots() -> None:
    html = """
    <html><head><title>Story</title></head><body><article>
      <p>Story text with enough content to be selected by readability.</p>
      <div class="c-ad advertising">
        <div class="c-ad__adzone"></div>
        <div class="c-ad__placeholder"><span>PUBLICIDAD</span></div>
      </div>
      <p>More story text after the ad.</p>
    </article></body></html>
    """

    _title, markdown, _fallback, _intro = extract_main_content(html, min_content_length=0)

    assert "Story text" in markdown
    assert "More story text" in markdown
    assert "PUBLICIDAD" not in markdown


def test_supplied_html_resolves_links_from_source_url() -> None:
    html = '<article><p>A reference to <a href="/other">another article</a>.</p></article>'
    _title, markdown, _fallback, _intro = extract_main_content(
        html, source_url="https://example.com/story"
    )
    metadata, body = split_front_matter(markdown)
    assert metadata["url"] == "https://example.com/story"
    assert "[another article](https://example.com/other)" in body


def test_extract_main_content_excludes_wikipedia_infoboxes() -> None:
    html = """
    <html><head><title>Jorge Luis Borges</title></head><body><article>
      <table class="infobox biography vcard">
        <tr><th>Jorge Luis Borges</th></tr>
        <tr><td>Información personal</td></tr>
      </table>
      <p>Jorge Luis Borges fue un escritor, poeta y ensayista argentino.</p>
    </article></body></html>
    """

    _title, markdown, _fallback, _intro = extract_main_content(html, min_content_length=0)

    assert "Jorge Luis Borges fue" in markdown
    assert "Información personal" not in markdown
