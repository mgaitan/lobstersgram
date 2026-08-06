"""Tests for the md-to-telegraph command-line interface."""

from __future__ import annotations

import io
import unittest.mock
from pathlib import Path

import pytest
from md_to_telegraph import cli

REQUEST_TIMEOUT = 7
RETRY_ATTEMPTS = 3


def test_main_reads_file_and_prints_page_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("# Article\n\nBody", encoding="utf-8")
    with unittest.mock.patch.object(cli, "create_page", return_value="https://telegra.ph/article") as create:
        assert cli.main([str(markdown_path), "--access-token", "token", "--no-warm-cache"]) == 0

    assert capsys.readouterr().out == "https://telegra.ph/article\n"
    create.assert_called_once_with(
        title="article",
        content_markdown="# Article\n\nBody",
        fallback_text="",
        source_url="",
        author_name="",
        access_token="token",
        request_timeout=20,
        retry_attempts=None,
        warm_cache=False,
    )


def test_main_reads_stdin_and_uses_explicit_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    with unittest.mock.patch.object(cli, "create_page", return_value="https://telegra.ph/stdin") as create:
        assert cli.main(
            [
                "--title",
                "From stdin",
                "--fallback-text",
                "Fallback",
                "--source-url",
                "https://example.com",
                "--author-name",
                "Author",
                "--access-token",
                "token",
                "--request-timeout",
                str(REQUEST_TIMEOUT),
                "--retry-attempts",
                str(RETRY_ATTEMPTS),
            ]
        ) == 0

    assert capsys.readouterr().out == "https://telegra.ph/stdin\n"
    assert create.call_args.kwargs["content_markdown"] == "Body"
    assert create.call_args.kwargs["title"] == "From stdin"
    assert create.call_args.kwargs["request_timeout"] == REQUEST_TIMEOUT
    assert create.call_args.kwargs["retry_attempts"] == RETRY_ATTEMPTS
    assert create.call_args.kwargs["warm_cache"] is True


def test_main_can_create_an_account(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "unused-environment-token")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    with (
        unittest.mock.patch.object(cli, "create_account", return_value="new-token") as create_account,
        unittest.mock.patch.object(cli, "create_page", return_value="https://telegra.ph/new") as create_page,
    ):
        assert cli.main(["--title", "A title", "--create-account", "--short-name", "custom"]) == 0

    assert capsys.readouterr().out == "https://telegra.ph/new\n"
    create_account.assert_called_once_with(
        short_name="custom",
        author_name="",
        author_url="",
        request_timeout=20,
        retry_attempts=None,
    )
    assert create_page.call_args.kwargs["access_token"] == "new-token"


def test_main_infers_title_from_stdin_heading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("# From Markdown\n\nBody"))
    with unittest.mock.patch.object(cli, "create_page", return_value="https://telegra.ph/inferred") as create:
        assert cli.main(["--access-token", "token"]) == 0

    assert capsys.readouterr().out == "https://telegra.ph/inferred\n"
    assert create.call_args.kwargs["title"] == "From Markdown"


def test_main_requires_title_when_stdin_has_no_heading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    with pytest.raises(SystemExit):
        cli.main([])

    assert "does not start with a Markdown heading" in capsys.readouterr().err


def test_main_reports_file_and_api_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(tmp_path / "missing.md")])
    assert "missing.md" in capsys.readouterr().err

    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("Body", encoding="utf-8")
    with (
        unittest.mock.patch.object(cli, "create_page", side_effect=cli.TelegraphTokenError()),
        pytest.raises(SystemExit),
    ):
        cli.main([str(markdown_path)])
    assert "TELEGRAPH_API_TOKEN" in capsys.readouterr().err
