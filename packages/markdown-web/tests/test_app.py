import markdown_web.app as app_module
import pytest
from fastapi.testclient import TestClient
from markdown_web.schemas import SourceMetadata, SourceRequest
from markdown_web.service import PreparedContent
from starlette.status import HTTP_200_OK, HTTP_303_SEE_OTHER, HTTP_422_UNPROCESSABLE_CONTENT

client = TestClient(app_module.app)


def _prepared(markdown: str = "# Title\n\nBody") -> PreparedContent:
    return PreparedContent("Title", markdown, "Fallback", SourceMetadata())


def test_home_and_static_assets() -> None:
    response = client.get("/")
    assert response.status_code == HTTP_200_OK
    assert "Turn any page into Markdown" in response.text
    assert client.get("/static/styles.css").status_code == HTTP_200_OK


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

    def fake_publish(source: SourceRequest, bookmarklet_key: str | None = None) -> str:
        seen["source"] = source
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


def test_get_telegraph_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "publish_content", lambda source: "https://telegra.ph/page")

    response = client.get("/t/https://example.com/article", follow_redirects=False)

    assert response.status_code == HTTP_303_SEE_OTHER
    assert response.headers["location"] == "https://telegra.ph/page"


def test_bookmarklet_form_does_not_expose_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "secret-token")

    response = client.post("/bookmarklet/", data={"access_token": "secret-token"})

    assert response.status_code == HTTP_200_OK
    assert "Save as Markdown" in response.text
    assert "javascript:" in response.text
    assert "secret-token" not in response.text


def test_invalid_post_source_returns_client_error() -> None:
    response = client.post("/md", json={})
    assert response.status_code == HTTP_422_UNPROCESSABLE_CONTENT
