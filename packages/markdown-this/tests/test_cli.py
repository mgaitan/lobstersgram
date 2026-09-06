"""Tests for the markdown-this command-line interface."""

from __future__ import annotations

import io

import pytest
from markdown_this import cli
from pytest_mock import MockerFixture


def test_main_reads_source_and_prints_markdown(capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture) -> None:
    extract = mocker.patch.object(
        cli,
        "extract_main_content",
        return_value=("Title", "# Title\n\nBody", "Body", "Body"),
    )
    assert cli.main(["article.html", "--request-timeout", "7"]) == 0

    assert capsys.readouterr().out == "# Title\n\nBody\n"
    extract.assert_called_once_with("article.html", request_timeout=7, min_content_length=200, intro_min_length=40)


def test_main_reads_html_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("<html><p>Body</p></html>"))
    extract = mocker.patch.object(
        cli,
        "extract_main_content",
        return_value=("Title", "Body", "Body", "Body"),
    )
    assert cli.main(["-", "--min-content-length", "0", "--intro-min-length", "5"]) == 0

    assert capsys.readouterr().out == "Body\n"
    extract.assert_called_once_with(
        "<html><p>Body</p></html>", request_timeout=20, min_content_length=0, intro_min_length=5
    )


def test_main_reports_extraction_errors(capsys: pytest.CaptureFixture[str], *, mocker: MockerFixture) -> None:
    mocker.patch.object(cli, "extract_main_content", side_effect=cli.ContentDownloadError)
    with pytest.raises(SystemExit):
        cli.main(["article.html"])

    assert "Failed to download content" in capsys.readouterr().err
