"""Tests for the md-to-telegraph command-line interface."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from md_to_telegraph import cli
from pytest_mock import MockerFixture

REQUEST_TIMEOUT = 7
RETRY_ATTEMPTS = 3


def test_main_reads_file_and_prints_page_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("# Article\n\nBody", encoding="utf-8")
    create = mocker.patch.object(cli, "create_page", return_value="https://telegra.ph/article")
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
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    create = mocker.patch.object(cli, "create_page", return_value="https://telegra.ph/stdin")
    assert (
        cli.main(
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
        )
        == 0
    )

    assert capsys.readouterr().out == "https://telegra.ph/stdin\n"
    assert create.call_args.kwargs["content_markdown"] == "Body"
    assert create.call_args.kwargs["title"] == "From stdin"
    assert create.call_args.kwargs["request_timeout"] == REQUEST_TIMEOUT
    assert create.call_args.kwargs["retry_attempts"] == RETRY_ATTEMPTS
    assert create.call_args.kwargs["warm_cache"] is True


def test_main_uses_front_matter_title_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    markdown = "---\ntitle: Header title\n---\n\nBody"
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(markdown))
    create = mocker.patch.object(cli, "create_page", return_value="https://telegra.ph/header")
    assert cli.main(["--access-token", "token"]) == 0

    assert capsys.readouterr().out == "https://telegra.ph/header\n"
    assert create.call_args.kwargs["title"] == "Header title"


def test_main_can_create_an_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    monkeypatch.setenv("TELEGRAPH_API_TOKEN", "unused-environment-token")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    create_account = mocker.patch.object(cli, "create_account", return_value="new-token")
    create_page = mocker.patch.object(cli, "create_page", return_value="https://telegra.ph/new")
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


def test_create_account_subcommand_prints_shell_assignment(
    capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    create_account = mocker.patch.object(cli, "create_account", return_value="new-token")
    assert (
        cli.main(
            [
                "create-account",
                "--short-name",
                "lobstersgram",
                "--author-name",
                "Author",
                "--author-url",
                "https://example.com",
                "--request-timeout",
                "7",
                "--retry-attempts",
                "3",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == "TELEGRAPH_API_TOKEN=new-token\n"
    create_account.assert_called_once_with(
        short_name="lobstersgram",
        author_name="Author",
        author_url="https://example.com",
        request_timeout=7,
        retry_attempts=3,
    )


def test_create_account_subcommand_uses_default_short_name(
    capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    create_account = mocker.patch.object(cli, "create_account", return_value="new-token")
    assert cli.main(["create-account"]) == 0

    assert capsys.readouterr().out == "TELEGRAPH_API_TOKEN=new-token\n"
    assert create_account.call_args.kwargs["short_name"] == "md-to-telegraph"


def test_create_account_subcommand_reports_api_errors(
    capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    mocker.patch.object(cli, "create_account", side_effect=cli.TelegraphAPIError({"error": "bad"}))
    with pytest.raises(SystemExit):
        cli.main(["create-account"])

    assert "Telegraph API error" in capsys.readouterr().err


def test_main_infers_title_from_stdin_heading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("# From Markdown\n\nBody"))
    create = mocker.patch.object(cli, "create_page", return_value="https://telegra.ph/inferred")
    assert cli.main(["--access-token", "token"]) == 0

    assert capsys.readouterr().out == "https://telegra.ph/inferred\n"
    assert create.call_args.kwargs["title"] == "From Markdown"


def test_main_requires_title_when_stdin_has_no_heading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("Body"))
    with pytest.raises(SystemExit):
        cli.main([])

    assert "no YAML title" in capsys.readouterr().err


def test_main_reports_file_and_api_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(tmp_path / "missing.md")])
    assert "missing.md" in capsys.readouterr().err

    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("Body", encoding="utf-8")
    mocker.patch.object(cli, "create_page", side_effect=cli.TelegraphTokenError())
    with pytest.raises(SystemExit):
        cli.main([str(markdown_path)])
    assert "TELEGRAPH_API_TOKEN" in capsys.readouterr().err
