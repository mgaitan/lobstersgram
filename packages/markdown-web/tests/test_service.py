import unittest.mock

import pytest
import requests
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


def test_prepare_content_converts_uploaded_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.anydoc, "to_markdown_bytes", lambda data, document_format: "# Report\n\nBody")

    result = service.prepare_content(SourceRequest(document=b"document", filename="report.epub"))

    assert result.title == "report"
    assert "title: report" in result.markdown
    assert result.fallback_text == "Report\n\nBody"


def test_prepare_content_downloads_document_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        content = b"document"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(service.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(service.anydoc, "to_markdown_bytes", lambda data, document_format: "# Report\n\nBody")

    result = service.prepare_content(SourceRequest(url="https://example.com/report.epub"))

    assert result.title == "report"
    assert "url: https://example.com/report.epub" in result.markdown


def test_prepare_content_keeps_markdown_front_matter() -> None:
    result = service.prepare_content(SourceRequest(markdown="---\ntitle: Existing\n---\n\n# Existing\n\nBody"))

    assert result.title == "Existing"
    assert result.fallback_text == "Existing\n\nBody"


def test_prepare_content_reads_telegram_recipients_from_front_matter() -> None:
    result = service.prepare_content(
        SourceRequest(markdown="---\ntitle: Existing\nnotify_telegram: 123, -100456\n---\n\nBody")
    )

    assert result.metadata.notify_telegram == "123, -100456"


def test_prepare_content_requires_a_source() -> None:
    with pytest.raises(service.SourceError, match="Provide one of"):
        service.prepare_content(SourceRequest())


def test_prepare_content_explains_when_source_denies_server_access(monkeypatch: pytest.MonkeyPatch) -> None:
    response = requests.Response()
    response.status_code = 401
    error = requests.HTTPError(response=response)
    monkeypatch.setattr(service, "extract_main_content", lambda _source: (_ for _ in ()).throw(error))

    with pytest.raises(service.SourceError, match="Send the page HTML through /bookmarklet/"):
        service.prepare_content(SourceRequest(url="https://example.com/article"))


def test_prepare_content_rejects_non_http_url() -> None:
    with pytest.raises(service.SourceError, match="http or https"):
        service.prepare_content(SourceRequest(url="file:///etc/passwd"))


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


def test_publish_content_passes_source_metadata_to_telegraph(monkeypatch: pytest.MonkeyPatch) -> None:
    published: dict[str, object] = {}

    def fake_create_page(**kwargs: object) -> str:
        published.update(kwargs)
        return "https://telegra.ph/page"

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setattr(service, "create_page", fake_create_page)

    service.publish_content(
        SourceRequest(markdown="---\ntitle: Title\nurl: https://www.pagina12.com.ar/article\n---\n\nBody")
    )

    assert published["source_url"] == "https://www.pagina12.com.ar/article"


def test_publish_content_notifies_telegram_recipients_with_only_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, bool]:
            return {"ok": True}

    def fake_post(url: str, **kwargs: object) -> Response:
        calls.append({"url": url, **kwargs})
        return Response()

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setenv("TELEGRAM_WEB_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(service, "create_page", lambda **_kwargs: "https://telegra.ph/page")
    monkeypatch.setattr(service.requests, "post", fake_post)

    result = service.publish_content(
        SourceRequest(markdown="---\nnotify_telegram: 123, -100456, 123\n---\n\n# Title\n\nBody")
    )

    assert result == "https://telegra.ph/page"
    assert calls == [
        {
            "url": "https://api.telegram.org/botbot-token/sendMessage",
            "json": {"chat_id": "123", "text": "https://telegra.ph/page"},
            "timeout": 20,
        },
        {
            "url": "https://api.telegram.org/botbot-token/sendMessage",
            "json": {"chat_id": "-100456", "text": "https://telegra.ph/page"},
            "timeout": 20,
        },
    ]


def test_publish_content_expands_cards_and_adds_article_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    brief_markdown = (
        "# Weekend brief\n\n"
        "## First article\n\n**Author** | **First medium**\n\n"
        "![card](https://example.com/one)\n\nFirst editorial paragraph.\n\n"
        "Second editorial paragraph.\n\n---\n\n"
        "## Second article\n\n**Author** | **Second medium**\n\n"
        "![card](https://example.com/two)\n\nAnother editorial paragraph."
    )
    brief = service.PreparedContent(
        "Weekend brief",
        brief_markdown,
        "Context",
        SourceMetadata(title="Weekend brief"),
    )
    articles = {
        "https://example.com/one": service.PreparedContent(
            "First article",
            "# First article\n\nFirst body",
            "First body",
            SourceMetadata(url="https://example.com/one", image="https://example.com/one.jpg"),
            "Why the first article matters.",
        ),
        "https://example.com/two": service.PreparedContent(
            "Second article",
            "# Second article\n\nSecond body",
            "Second body",
            SourceMetadata(url="https://example.com/two"),
            "Why the second article matters.",
        ),
    }

    def fake_prepare(request: SourceRequest) -> service.PreparedContent:
        return articles[request.url] if request.url else brief

    create_calls: list[dict[str, object]] = []
    created_urls = iter(
        [
            "https://telegra.ph/First-article-08-30",
            "https://telegra.ph/Second-article-08-30",
            "https://telegra.ph/Weekend-brief-08-30",
        ]
    )

    def fake_create_page(**kwargs: object) -> str:
        create_calls.append(kwargs)
        return next(created_urls)

    edit_calls: list[dict[str, object]] = []

    def fake_edit_page(**kwargs: object) -> str:
        edit_calls.append(kwargs)
        return f"https://telegra.ph/{kwargs['path']}"

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setattr(service, "prepare_content", fake_prepare)
    monkeypatch.setattr(service, "create_page", fake_create_page)
    monkeypatch.setattr(service, "edit_page", fake_edit_page)

    result = service.publish_content(SourceRequest(markdown=brief_markdown))

    assert result == "https://telegra.ph/Weekend-brief-08-30"
    assert len(create_calls) == len(articles) + 1
    published_brief = str(create_calls[-1]["content_markdown"])
    assert "![card]" not in published_brief
    assert "https://telegra.ph/First-article-08-30" in published_brief
    assert "https://example.com/one.jpg" in published_brief
    assert "Why the first article matters." not in published_brief
    assert published_brief.index("https://example.com/one.jpg") < published_brief.index("First editorial paragraph.")
    assert published_brief.index("First editorial paragraph.") < published_brief.index("Leer en Telegraph")
    assert published_brief.count("Leer en Telegraph") == len(articles)
    assert len(edit_calls) == len(articles)
    first_navigation = str(edit_calls[0]["content_markdown"])
    second_navigation = str(edit_calls[1]["content_markdown"])
    assert "Volver al boletín](https://telegra.ph/Weekend-brief-08-30)" in first_navigation
    assert "Artículo siguiente](https://telegra.ph/Second-article-08-30)" in first_navigation
    assert "Artículo anterior" not in first_navigation
    assert "Artículo anterior](https://telegra.ph/First-article-08-30)" in second_navigation
    assert "Artículo siguiente" not in second_navigation


def test_publish_content_reuses_a_repeated_card_within_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    source_url = "https://example.com/repeated"
    brief_markdown = f"# Brief\n\n![card]({source_url})\n\n![card]({source_url})"
    brief = service.PreparedContent("Brief", brief_markdown, "", SourceMetadata())
    article = service.PreparedContent("Article", "Body", "Body", SourceMetadata(url=source_url))

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setattr(
        service,
        "prepare_content",
        lambda request: article if request.url else brief,
    )
    create = unittest.mock.Mock(side_effect=["https://telegra.ph/Article-08-30", "https://telegra.ph/Brief-08-30"])
    monkeypatch.setattr(service, "create_page", create)
    monkeypatch.setattr(service, "edit_page", unittest.mock.Mock(return_value="https://telegra.ph/Article-08-30"))

    assert service.publish_content(SourceRequest(markdown=brief_markdown)) == "https://telegra.ph/Brief-08-30"
    assert create.call_count == len({source_url}) + 1
    published_brief = str(create.call_args_list[-1].kwargs["content_markdown"])
    assert published_brief.count("https://telegra.ph/Article-08-30") == brief_markdown.count("![card]")


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


def test_list_published_pages_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, pages: list[dict[str, object]]) -> None:
            self.pages = pages

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "result": {"total_count": 2, "pages": self.pages}}

    calls: list[dict[str, object]] = []
    responses = [
        FakeResponse([{"url": "https://telegra.ph/one", "title": "One"}]),
        FakeResponse([{"url": "https://telegra.ph/two", "title": "Two"}]),
    ]

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return responses.pop(0)

    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    monkeypatch.setattr(service.requests, "get", fake_get)

    total, pages = service.list_published_pages()

    expected_total = 2
    assert total == expected_total
    assert pages == [
        {"url": "https://telegra.ph/one", "title": "One"},
        {"url": "https://telegra.ph/two", "title": "Two"},
    ]
    assert [call["params"] for call in calls] == [
        {"access_token": "environment-token", "offset": 0, "limit": 200},
        {"access_token": "environment-token", "offset": 1, "limit": 200},
    ]
