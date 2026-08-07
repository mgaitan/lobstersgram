"""Tests for the Telegraph API client."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest
import requests
from md_to_telegraph import (
    TelegraphAPIError,
    TelegraphContentError,
    TelegraphTitleError,
    TelegraphTokenError,
    create_account,
    create_page,
    warm_telegraph_cache,
)
from md_to_telegraph import telegraph as telegraph_module

HTTP_CLIENT_ERROR_MIN = 400
MAX_TITLE_LENGTH = 256


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


def test_create_page_posts_content_and_warms_cache() -> None:
    post_response = _success_response()
    cache_response = FakeResponse(200, {})
    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", return_value=post_response) as post,
        unittest.mock.patch.object(telegraph_module.requests, "get", return_value=cache_response) as get,
    ):
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


def test_create_page_without_retry_or_cache() -> None:
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
        result = create_page(
            access_token="token",
            title="Title",
            content_markdown="",
            fallback_text="Fallback",
            warm_cache=False,
        )

    assert result == "https://telegra.ph/page"
    post.assert_called_once()


def test_create_page_reads_token_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "environment-token")
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
        create_page("Title", "Body", warm_cache=False)

    assert post.call_args.kwargs["data"]["access_token"] == "environment-token"


def test_create_page_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAPH_API_TOKEN", raising=False)
    with pytest.raises(TelegraphTokenError):
        create_page("Title", "Body", warm_cache=False)


def test_create_page_reads_markdown_path_and_removes_duplicate_title_heading(tmp_path: Path) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("\n\n# Final title\n\nBody", encoding="utf-8")
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
        create_page("Final title", markdown_path, access_token="token", warm_cache=False)

    payload = post.call_args.kwargs["data"]
    assert json.loads(payload["content"]) == [{"tag": "p", "children": ["Body"]}]


def test_create_page_reads_front_matter_defaults() -> None:
    markdown = (
        "---\ntitle: Front matter title\nauthor: Author\nurl: https://example.com\n"
        "date: 2026-08-06\nimage: https://example.com/hero.jpg\n---\n\nBody"
    )
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
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


def test_create_page_uses_source_domain_as_default_author() -> None:
    markdown = "---\ntitle: Article\nurl: https://www.pagina12.com.ar/article\n---\n\nBody"
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
        create_page(content_markdown=markdown, access_token="token", warm_cache=False)

    payload = post.call_args.kwargs["data"]
    assert payload["author_name"] == "pagina12.com.ar"
    assert payload["author_url"] == "https://www.pagina12.com.ar/article"


def test_create_page_handles_non_json_api_response() -> None:
    response = unittest.mock.Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError

    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", return_value=response),
        pytest.raises(TelegraphAPIError) as exc_info,
    ):
        create_page("Title", "Body", access_token="token", warm_cache=False)

    assert exc_info.value.data == {"ok": False, "error": "invalid_json_response"}


def test_create_page_does_not_duplicate_front_matter_image() -> None:
    markdown = "---\nimage: https://example.com/hero.jpg\n---\n\n![Hero](https://example.com/hero.jpg)"
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
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


def test_create_page_explicit_values_override_front_matter() -> None:
    markdown = "---\ntitle: Header title\nauthor: Header author\nurl: https://header.example\n---\n\nBody"
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
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


def test_create_page_uses_path_stem_without_title(tmp_path: Path) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("Body", encoding="utf-8")
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()) as post:
        create_page(content_markdown=markdown_path, access_token="token", warm_cache=False)

    assert post.call_args.kwargs["data"]["title"] == "article"


def test_create_page_requires_a_title_for_raw_markdown() -> None:
    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_success_response()),
        pytest.raises(TelegraphTitleError),
    ):
        create_page(content_markdown="Body", access_token="token", warm_cache=False)


def test_create_account_posts_account_details() -> None:
    with unittest.mock.patch.object(telegraph_module.requests, "post", return_value=_account_response()) as post:
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


def test_create_account_rejects_missing_token_in_response() -> None:
    with (
        unittest.mock.patch.object(
            telegraph_module.requests, "post", return_value=FakeResponse(200, {"ok": True, "result": {}})
        ),
        pytest.raises(TelegraphAPIError),
    ):
        create_account("short-name")


def test_create_page_retries_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [FakeResponse(500, {}), _success_response()]
    with unittest.mock.patch.object(telegraph_module.requests, "post", side_effect=responses):
        sleep = unittest.mock.Mock()
        monkeypatch.setattr(telegraph_module.time, "sleep", sleep)
        result = create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert result == "https://telegra.ph/page"
    sleep.assert_called_once_with(2.0)


def test_create_page_retries_unsuccessful_api_response() -> None:
    responses = [FakeResponse(200, {"ok": False, "error": "temporary"}), _success_response()]
    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", side_effect=responses),
        unittest.mock.patch.object(telegraph_module.time, "sleep"),
    ):
        result = create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert result == "https://telegra.ph/page"


def test_create_page_raises_after_api_retries() -> None:
    response = FakeResponse(200, {"ok": False, "error": "permanent"})
    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", return_value=response),
        unittest.mock.patch.object(telegraph_module.time, "sleep"),
        pytest.raises(TelegraphAPIError) as exc_info,
    ):
        create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)

    assert exc_info.value.data == {"ok": False, "error": "permanent"}


def test_create_page_raises_for_final_server_error() -> None:
    with (
        unittest.mock.patch.object(telegraph_module.requests, "post", return_value=FakeResponse(500, {})),
        pytest.raises(requests.HTTPError),
    ):
        create_page("Title", "Body", access_token="token", retry_attempts=2, warm_cache=False)


def test_warm_telegraph_cache_ignores_request_errors() -> None:
    with unittest.mock.patch.object(
        telegraph_module.requests, "get", side_effect=requests.RequestException("network down")
    ):
        warm_telegraph_cache("https://telegra.ph/page")
