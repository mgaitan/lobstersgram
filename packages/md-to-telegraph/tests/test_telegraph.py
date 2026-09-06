"""Tests for the Telegraph API client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from md_to_telegraph import (
    TelegraphAPIError,
    TelegraphContentError,
    TelegraphPages,
    TelegraphTitleError,
    TelegraphTokenError,
    create_account,
    create_page,
    create_pages,
    edit_page,
    page_navigation,
    split_markdown_pages,
    warm_telegraph_cache,
)
from md_to_telegraph import telegraph as telegraph_module
from pytest_mock import MockerFixture

HTTP_CLIENT_ERROR_MIN = 400
MAX_TITLE_LENGTH = 256
PAGE_LIMIT = 30
MIN_PAGE_COUNT = 2
EXPECTED_SHORT_PAGE_COUNT = 2


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, object]) -> None:
        self.status_code = status_code
        self._data = data

    def raise_for_status(self) -> None:
        if self.status_code >= HTTP_CLIENT_ERROR_MIN:
            raise requests.HTTPError

    def json(self) -> dict[str, object]:
        return self._data


def _success_response(url: str = "https://telegra.ph/page") -> FakeResponse:
    return FakeResponse(200, {"ok": True, "result": {"url": url}})


def _account_response(token: str = "new-token") -> FakeResponse:
    return FakeResponse(200, {"ok": True, "result": {"access_token": token}})


def test_create_page_posts_content_and_warms_cache(*, mocker: MockerFixture) -> None:
    post_response = _success_response()
    cache_response = FakeResponse(200, {})
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=post_response)
    get = mocker.patch.object(telegraph_module.requests, "get", return_value=cache_response)
    result = create_page(
        access_token="token",
        title="A" * 300,
        content_markdown="# Article\n\nBody",
        fallback_text="Fallback",
        source_url="https://example.com/article",
        author_name="Source",
        request_timeout=7,
    )

    assert result == "https://telegra.ph/page"
    payload = post.call_args.kwargs["data"]
    assert payload["access_token"] == "token"
    assert len(payload["title"]) == MAX_TITLE_LENGTH
    assert payload["author_name"] == "Source"
    assert payload["author_url"] == "https://example.com/article"
    assert json.loads(payload["content"]) == [
        {"tag": "h3", "children": ["Article"]},
        {"tag": "p", "children": ["Body"]},
    ]
    post.assert_called_once_with(
        "https://api.telegra.ph/createPage",
        data=payload,
        timeout=7,
    )
    get.assert_called_once_with(
        "https://telegra.ph/page",
        timeout=7,
        headers={"User-Agent": "md-to-telegraph"},
    )


def test_create_page_without_retry_or_cache(*, mocker: MockerFixture) -> None:
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    result = create_page(
        access_token="token",
        title="Title",
        content_markdown="",
        fallback_text="Fallback",
        warm_cache=False,
    )

    assert result == "https://telegra.ph/page"
    post.assert_called_once()


def test_edit_page_posts_path_and_replacement_content(*, mocker: MockerFixture) -> None:
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    warm_cache = mocker.patch.object(telegraph_module, "warm_telegraph_cache")
    result = edit_page(
        path="Article-08-30",
        title="Article",
        content_markdown="Updated body",
        access_token="token",
    )

    assert result == "https://telegra.ph/page"
    payload = post.call_args.kwargs["data"]
    assert payload["path"] == "Article-08-30"
    assert json.loads(payload["content"]) == [{"tag": "p", "children": ["Updated body"]}]
    post.assert_called_once_with(
        "https://api.telegra.ph/editPage",
        data=payload,
        timeout=20,
    )
    warm_cache.assert_called_once_with("https://telegra.ph/page", 20)


def test_create_page_reads_token_from_environment(monkeypatch: pytest.MonkeyPatch, *, mocker: MockerFixture) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page("Title", "Body", warm_cache=False)

    assert post.call_args.kwargs["data"]["access_token"] == "environment-token"


def test_create_page_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAPH_API_TOKEN", raising=False)
    with pytest.raises(TelegraphTokenError):
        create_page("Title", "Body", warm_cache=False)


def test_create_page_reads_markdown_path_and_removes_duplicate_title_heading(
    tmp_path: Path, *, mocker: MockerFixture
) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("\n\n# Final title\n\nBody", encoding="utf-8")
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page("Final title", markdown_path, access_token="token", warm_cache=False)

    payload = post.call_args.kwargs["data"]
    assert json.loads(payload["content"]) == [{"tag": "p", "children": ["Body"]}]


def test_create_page_reads_front_matter_defaults(*, mocker: MockerFixture) -> None:
    markdown = (
        "---\ntitle: Front matter title\nauthor: Author\nurl: https://example.com\n"
        "date: 2026-08-06\nimage: https://example.com/hero.jpg\n---\n\nBody"
    )
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page(content_markdown=markdown, access_token="token", warm_cache=False)

    payload = post.call_args.kwargs["data"]
    assert payload["title"] == "Front matter title"
    assert payload["author_name"] == "Author"
    assert payload["author_url"] == "https://example.com"
    assert json.loads(payload["content"]) == [
        {"tag": "img", "attrs": {"src": "https://example.com/hero.jpg"}},
        {"tag": "p", "children": ["Body"]},
    ]


def test_create_page_rejects_non_document_page_type() -> None:
    markdown = "---\ntitle: LA NACION\ntype: website\n---\n\nHome links"

    with pytest.raises(TelegraphContentError, match="non-document"):
        create_page(content_markdown=markdown, access_token="token", warm_cache=False)


def test_create_page_uses_source_domain_as_default_author(*, mocker: MockerFixture) -> None:
    markdown = "---\ntitle: Article\nurl: https://www.pagina12.com.ar/article\n---\n\nBody"
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page(content_markdown=markdown, access_token="token", warm_cache=False)

    payload = post.call_args.kwargs["data"]
    assert payload["author_name"] == "pagina12.com.ar"
    assert payload["author_url"] == "https://www.pagina12.com.ar/article"


def test_create_page_handles_non_json_api_response(*, mocker: MockerFixture) -> None:
    response = mocker.Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError
    mocker.patch.object(telegraph_module.requests, "post", return_value=response)

    with pytest.raises(TelegraphAPIError) as exc_info:
        create_page("Title", "Body", access_token="token", warm_cache=False)

    assert exc_info.value.data == {"ok": False, "error": "invalid_json_response"}


def test_create_page_does_not_duplicate_front_matter_image(*, mocker: MockerFixture) -> None:
    markdown = "---\nimage: https://example.com/hero.jpg\n---\n\n![Hero](https://example.com/hero.jpg)"
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page(
        title="Title",
        content_markdown=markdown,
        access_token="token",
        warm_cache=False,
    )

    assert json.loads(post.call_args.kwargs["data"]["content"]) == [
        {
            "tag": "p",
            "children": [
                {
                    "tag": "img",
                    "attrs": {"src": "https://example.com/hero.jpg", "alt": ["Hero"]},
                }
            ],
        }
    ]


def test_create_page_explicit_values_override_front_matter(*, mocker: MockerFixture) -> None:
    markdown = "---\ntitle: Header title\nauthor: Header author\nurl: https://header.example\n---\n\nBody"
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page(
        title="Explicit title",
        content_markdown=markdown,
        author_name="Explicit author",
        source_url="https://explicit.example",
        access_token="token",
        warm_cache=False,
    )

    payload = post.call_args.kwargs["data"]
    assert payload["title"] == "Explicit title"
    assert payload["author_name"] == "Explicit author"
    assert payload["author_url"] == "https://explicit.example"


def test_create_page_uses_path_stem_without_title(tmp_path: Path, *, mocker: MockerFixture) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("Body", encoding="utf-8")
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    create_page(content_markdown=markdown_path, access_token="token", warm_cache=False)

    assert post.call_args.kwargs["data"]["title"] == "article"


def test_create_page_requires_a_title_for_raw_markdown(*, mocker: MockerFixture) -> None:
    mocker.patch.object(telegraph_module.requests, "post", return_value=_success_response())
    with pytest.raises(TelegraphTitleError):
        create_page(content_markdown="Body", access_token="token", warm_cache=False)


def test_split_markdown_pages_preserves_complete_blocks() -> None:
    markdown = "First paragraph\n\nSecond paragraph\n\nLast paragraph"

    pages = split_markdown_pages(markdown, max_chars=len("First paragraph\n\nSecond paragraph"))

    assert len(pages) == MIN_PAGE_COUNT
    assert pages[0] == "First paragraph\n\nSecond paragraph"
    assert "Last paragraph" in pages[-1]


def test_split_markdown_pages_keeps_oversized_blocks_intact() -> None:
    block = "x" * (PAGE_LIMIT + 1)

    assert split_markdown_pages(block, max_chars=PAGE_LIMIT) == [block]


def test_split_markdown_pages_keeps_fenced_code_with_internal_blank_lines() -> None:
    code_block = "```python\nfirst\n\nsecond\n```"
    markdown = f"Intro\n\n{code_block}\n\nEnd"

    pages = split_markdown_pages(markdown, max_chars=len("Intro"))

    assert code_block in pages


def test_split_markdown_pages_returns_empty_body_when_markdown_is_empty() -> None:
    assert split_markdown_pages("---\ntitle: Empty\n---\n", max_chars=30) == [""]


def test_page_navigation_links_adjacent_pages() -> None:
    urls = ("https://telegra.ph/one", "https://telegra.ph/two", "https://telegra.ph/three")

    assert page_navigation(urls, 0) == "\n\n---\n\n[Página siguiente](https://telegra.ph/two)"
    assert "Página anterior" in page_navigation(urls, 1)
    assert page_navigation(urls, 2).endswith("[Página anterior](https://telegra.ph/two)")
    assert page_navigation((urls[0],), 0) == ""


def test_create_pages_creates_and_links_long_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, object]] = []
    edited: list[dict[str, object]] = []

    def fake_create_page(**kwargs: object) -> str:
        created.append(kwargs)
        return f"https://telegra.ph/page-{len(created)}"

    def fake_edit_page(**kwargs: object) -> str:
        edited.append(kwargs)
        return str(kwargs["path"])

    monkeypatch.setattr(telegraph_module, "create_page", fake_create_page)
    monkeypatch.setattr(telegraph_module, "edit_page", fake_edit_page)
    markdown = "---\ntitle: Long title\nauthor: Author\n---\n\n" + "\n\n".join(
        f"Paragraph {index}: " + "readable content " * 8 for index in range(1, 4)
    )

    pages = create_pages(
        content_markdown=markdown,
        access_token="token",
        max_chars=30,
        warm_cache=False,
    )

    assert isinstance(pages, TelegraphPages)
    assert len(pages.urls) > 1
    assert len(created) == len(edited) == len(pages.urls)
    assert created[0]["title"] == "Long title"
    assert created[0]["warm_cache"] is False
    assert "Página siguiente" in str(edited[0]["content_markdown"])
    assert "Página anterior" in str(edited[-1]["content_markdown"])
    assert all("author: Author" in page for page in pages.markdowns)


def test_create_pages_handles_long_markdown_without_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegraph_module, "create_page", lambda **kwargs: "https://telegra.ph/page")
    monkeypatch.setattr(telegraph_module, "edit_page", lambda **kwargs: "https://telegra.ph/page")

    pages = create_pages(
        title="Long title",
        content_markdown="\n\n".join("paragraph " + ("x" * 20) for _ in range(2)),
        access_token="token",
        max_chars=PAGE_LIMIT,
        warm_cache=False,
    )

    assert len(pages.urls) == EXPECTED_SHORT_PAGE_COUNT


def test_create_pages_uses_create_page_for_short_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_page(**kwargs: object) -> str:
        calls.append(kwargs)
        return "https://telegra.ph/short"

    monkeypatch.setattr(telegraph_module, "create_page", fake_create_page)

    pages = create_pages(title="Short", content_markdown="Body", access_token="token", warm_cache=False)

    assert pages == TelegraphPages(("https://telegra.ph/short",), ("Body",))
    assert calls[0]["warm_cache"] is False


def test_create_account_posts_account_details(*, mocker: MockerFixture) -> None:
    post = mocker.patch.object(telegraph_module.requests, "post", return_value=_account_response())
    token = create_account(
        "short-name",
        author_name="Author",
        author_url="https://example.com/author",
        request_timeout=9,
    )

    assert token == "new-token"
    post.assert_called_once_with(
        "https://api.telegra.ph/createAccount",
        data={
            "short_name": "short-name",
            "author_name": "Author",
            "author_url": "https://example.com/author",
        },
        timeout=9,
    )


def test_create_account_rejects_missing_token_in_response(*, mocker: MockerFixture) -> None:
    mocker.patch.object(telegraph_module.requests, "post", return_value=FakeResponse(200, {"ok": True, "result": {}}))
    with pytest.raises(TelegraphAPIError):
        create_account("short-name")


def test_create_page_retries_server_error(monkeypatch: pytest.MonkeyPatch, *, mocker: MockerFixture) -> None:
    responses = [FakeResponse(500, {}), _success_response()]
    mocker.patch.object(telegraph_module.requests, "post", side_effect=responses)
    sleep = mocker.Mock()
    monkeypatch.setattr(telegraph_module.time, "sleep", sleep)
    result = create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert result == "https://telegra.ph/page"
    sleep.assert_called_once_with(2.0)


def test_create_page_retries_unsuccessful_api_response(*, mocker: MockerFixture) -> None:
    responses = [FakeResponse(200, {"ok": False, "error": "temporary"}), _success_response()]
    mocker.patch.object(telegraph_module.requests, "post", side_effect=responses)
    mocker.patch.object(telegraph_module.time, "sleep")
    result = create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert result == "https://telegra.ph/page"


def test_create_page_raises_after_api_retries(*, mocker: MockerFixture) -> None:
    response = FakeResponse(200, {"ok": False, "error": "permanent"})
    mocker.patch.object(telegraph_module.requests, "post", return_value=response)
    mocker.patch.object(telegraph_module.time, "sleep")
    with pytest.raises(TelegraphAPIError) as exc_info:
        create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert exc_info.value.data == {"ok": False, "error": "permanent"}


def test_create_page_raises_for_final_server_error(*, mocker: MockerFixture) -> None:
    mocker.patch.object(telegraph_module.requests, "post", return_value=FakeResponse(500, {}))
    with pytest.raises(requests.HTTPError):
        create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)


def test_warm_telegraph_cache_ignores_request_errors(*, mocker: MockerFixture) -> None:
    mocker.patch.object(telegraph_module.requests, "get", side_effect=requests.RequestException("network down"))
    warm_telegraph_cache("https://telegra.ph/page")
