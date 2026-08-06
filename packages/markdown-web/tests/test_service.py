import pytest
from markdown_web import service
from markdown_web.schemas import SourceMetadata, SourceRequest


def test_prepare_content_extracts_url_and_merges_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "extract_main_content",
        lambda source: ("Extracted title", "# Extracted title\n\nBody", "Fallback", "Intro"),
    )

    result = service.prepare_content(
        SourceRequest(
            url="https://example.com/article",
            metadata=SourceMetadata(author="Author", image="https://example.com/image.jpg"),
        )
    )

    assert result.title == "Extracted title"
    assert "author: Author" in result.markdown
    assert "image: https://example.com/image.jpg" in result.markdown
    assert result.fallback_text == "Fallback"


def test_prepare_content_accepts_raw_html(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "extract_main_content",
        lambda source: ("HTML title", "HTML body", "Fallback", "Intro"),
    )

    result = service.prepare_content(
        SourceRequest(html="<h1>HTML title</h1>", metadata=SourceMetadata(url="https://example.com"))
    )

    assert result.title == "HTML title"
    assert "url: https://example.com" in result.markdown


def test_prepare_content_keeps_markdown_front_matter() -> None:
    result = service.prepare_content(SourceRequest(markdown="---\ntitle: Existing\n---\n\n# Existing\n\nBody"))

    assert result.title == "Existing"
    assert result.fallback_text == "Existing\n\nBody"


def test_prepare_content_requires_a_source() -> None:
    with pytest.raises(service.SourceError, match="Provide one of"):
        service.prepare_content(SourceRequest())


def test_prepare_content_rejects_non_http_url() -> None:
    with pytest.raises(service.SourceError, match="http or https"):
        service.prepare_content(SourceRequest(url="file:///etc/passwd"))


def test_bookmarklet_token_store_rejects_unknown_key() -> None:
    with pytest.raises(service.SourceError, match="Unknown or expired"):
        service.require_bookmarklet_token("missing")


def test_publish_content_passes_resolved_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    published: dict[str, object] = {}

    def fake_create_page(**kwargs: object) -> str:
        published.update(kwargs)
        return "https://telegra.ph/page"

    monkeypatch.setattr(service, "create_page", fake_create_page)

    result = service.publish_content(SourceRequest(markdown="# Title\n\nBody"))

    assert result == "https://telegra.ph/page"
    assert published["access_token"] == "environment-token"


def test_publish_content_reuses_cached_source_url(monkeypatch: pytest.MonkeyPatch) -> None:
    service.published_urls.clear()
    calls = 0

    def fake_create_page(**kwargs: object) -> str:
        nonlocal calls
        calls += 1
        return "https://telegra.ph/cached"

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setattr(service, "create_page", fake_create_page)
    source = SourceRequest(markdown="# Title\n\nBody")

    first = service.publish_content(source, cache_key="https://example.com")
    second = service.publish_content(source, cache_key="https://example.com")

    assert first == second == "https://telegra.ph/cached"
    assert calls == 1
