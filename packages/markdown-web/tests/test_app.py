import markdown_web.app as app_module
import pytest
from fastapi.testclient import TestClient
from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.service import PreparedContent
from md_to_telegraph import TelegraphContentError
from starlette.status import (
    HTTP_200_OK,
    HTTP_303_SEE_OTHER,
    HTTP_422_UNPROCESSABLE_CONTENT,
)

client = TestClient(app_module.app)


def _prepared(markdown: str = "# Title\n\nBody") -> PreparedContent:
    return PreparedContent("Title", markdown, "Fallback", SourceMetadata())


def test_home_and_static_assets() -> None:
    response = client.get("/")
    assert response.status_code == HTTP_200_OK
    assert "Turn any page into Markdown or publish it to Telegraph" in response.text
    assert ">markdown-web<" not in response.text
    assert 'href="/bookmarklets/">Bookmarklets</a>' in response.text
    assert 'property="og:title" content="Markdown and Telegraph"' in response.text
    assert (
        'property="og:description" content="Turn any page into Markdown or publish it to Telegraph."' in response.text
    )
    assert 'name="twitter:card" content="summary"' in response.text
    assert client.get("/static/styles.css").status_code == HTTP_200_OK


def test_about_describes_routes_and_cli() -> None:
    response = client.get("/about")

    assert response.status_code == HTTP_200_OK
    assert "/md/&lt;url&gt;" in response.text
    assert "/t/published/" in response.text
    assert "uvx markdown-this" in response.text
    assert "github.com/mgaitan" in response.text


def test_search_engine_discovery_metadata() -> None:
    about_response = client.get("/about")
    bookmarklet_response = client.get("/bookmarklets/")
    sitemap_response = client.get("/sitemap.xml")
    robots_response = client.get("/robots.txt")

    assert 'name="robots" content="index,follow"' in about_response.text
    assert 'rel="canonical" href="https://markdown.fastapicloud.dev/about"' in about_response.text
    assert 'rel="canonical" href="https://markdown.fastapicloud.dev/bookmarklets/"' in bookmarklet_response.text
    assert "https://markdown.fastapicloud.dev/about" in sitemap_response.text
    assert "https://markdown.fastapicloud.dev/bookmarklets/" in sitemap_response.text
    assert "Sitemap: https://markdown.fastapicloud.dev/sitemap.xml" in robots_response.text


def test_get_markdown_uses_jina_style_path_and_preserves_query(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_prepare(source: SourceRequest) -> PreparedContent:
        seen.append(source.url)
        return _prepared()

    monkeypatch.setattr(app_module, "prepare_content", fake_prepare)

    response = client.get("/md/https://example.com/article?edition=mobile")

    assert response.status_code == HTTP_200_OK
    assert response.text == "# Title\n\nBody"
    assert seen == ["https://example.com/article?edition=mobile"]


def test_post_markdown_accepts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "prepare_content", lambda source: _prepared("# From JSON"))

    response = client.post("/md", json={"url": "https://example.com"})

    assert response.status_code == HTTP_200_OK
    assert response.text == "# From JSON"
    assert response.headers["content-type"].startswith("text/markdown")


def test_post_markdown_accepts_raw_html_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, SourceRequest] = {}

    def fake_prepare(source: SourceRequest) -> PreparedContent:
        seen["source"] = source
        return _prepared("# From HTML")

    monkeypatch.setattr(app_module, "prepare_content", fake_prepare)

    response = client.post(
        "/md",
        content="<h1>From HTML</h1>",
        headers={"content-type": "text/html", "x-source-url": "https://example.com"},
    )

    assert response.status_code == HTTP_200_OK
    assert seen["source"].html == "<h1>From HTML</h1>"
    assert seen["source"].metadata.url == "https://example.com"


def test_post_telegraph_returns_json_and_accepts_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, SourceRequest] = {}

    def fake_publish(
        source: SourceRequest,
        cache_key: str | None = None,
    ) -> str:
        seen["source"] = source
        seen["cache_key"] = cache_key
        return "https://telegra.ph/page"

    monkeypatch.setattr(app_module, "publish_content", fake_publish)

    response = client.post(
        "/t",
        json={"markdown": "# Title"},
        headers={"authorization": "Bearer request-token"},
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"url": "https://telegra.ph/page"}
    assert seen["source"].access_token == "request-token"


def test_bookmarklet_post_redirects_without_fetch_or_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, SourceRequest] = {}

    def fake_publish(source: SourceRequest, cache_key: str | None = None) -> str:
        seen["source"] = source
        return "https://telegra.ph/page"

    monkeypatch.setattr(app_module, "publish_content", fake_publish)

    response = client.post(
        "/t/bookmarklet",
        data={
            "html": "<h1>Title</h1><p>Body</p>",
            "title": "Title",
            "source_url": "https://chatgpt.com/c/example",
        },
        follow_redirects=False,
    )

    assert response.status_code == HTTP_303_SEE_OTHER
    assert response.headers["location"] == "https://telegra.ph/page"
    assert seen["source"].html == "<h1>Title</h1><p>Body</p>"
    assert seen["source"].metadata.url == "https://chatgpt.com/c/example"


def test_post_telegraph_rejects_non_document_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_source(source: SourceRequest, cache_key: str | None = None) -> str:
        raise TelegraphContentError("website")

    monkeypatch.setattr(app_module, "publish_content", reject_source)

    response = client.post("/t", json={"markdown": "---\ntype: website\n---\n\nHome"})

    assert response.status_code == HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": "Refusing to publish non-document page (type: website)"}


def test_get_telegraph_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_publish(
        source: SourceRequest,
        cache_key: str | None = None,
    ) -> str:
        seen["source"] = source
        seen["cache_key"] = cache_key
        return "https://telegra.ph/page"

    monkeypatch.setattr(app_module, "publish_content", fake_publish)

    response = client.get("/t/https://example.com/article", follow_redirects=False)

    assert response.status_code == HTTP_303_SEE_OTHER
    assert response.headers["location"] == "https://telegra.ph/page"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert seen["cache_key"] == "https://example.com/article"


def test_telegraph_published_lists_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_module,
        "list_published_pages",
        lambda: (
            1,
            [
                {
                    "url": "https://telegra.ph/Article-08-07",
                    "title": "Article",
                    "author_url": "https://example.com/article",
                    "views": 12,
                }
            ],
        ),
    )

    response = client.get("/t/published/")

    assert response.status_code == HTTP_200_OK
    assert "Published pages" in response.text
    assert 'href="https://telegra.ph/Article-08-07"' in response.text
    assert 'href="https://example.com/article"' in response.text
    assert "12 views" in response.text


def test_bookmarklet_form_does_not_expose_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "secret-token")

    response = client.get("/bookmarklet/")

    assert response.status_code == HTTP_200_OK
    assert "Save as Markdown" in response.text
    assert "javascript:" in response.text
    assert "secret-token" not in response.text
    assert "Generate bookmarklets" not in response.text
    assert "Drag either link" in response.text


def test_invalid_post_source_returns_client_error() -> None:
    response = client.post("/md", json={})
    assert response.status_code == HTTP_422_UNPROCESSABLE_CONTENT
