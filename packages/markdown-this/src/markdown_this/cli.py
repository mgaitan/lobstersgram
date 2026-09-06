"""Command-line interface for extracting readable Markdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from markdown_this.extractor import ContentDownloadError, extract_main_content


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract readable Markdown from a URL, file, or HTML")
    parser.add_argument(
        "source",
        nargs="?",
        help="URL, HTML file, or -; read raw HTML from stdin when omitted",
    )
    parser.add_argument("--request-timeout", type=int, default=20)
    parser.add_argument("--source-url", default="", help="Original URL for HTML supplied as a file or stdin")
    parser.add_argument("--min-content-length", type=int, default=200)
    parser.add_argument("--intro-min-length", type=int, default=40)
    return parser


def _read_source(source: str | None) -> Path | str:
    if source in (None, "-"):
        return sys.stdin.read()
    return source


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        _title, markdown, _fallback_text, _intro = extract_main_content(
            _read_source(args.source),
            request_timeout=args.request_timeout,
            min_content_length=args.min_content_length,
            intro_min_length=args.intro_min_length,
            source_url=args.source_url,
        )
    except (ContentDownloadError, OSError, requests.RequestException) as exc:
        parser.error(str(exc))

    print(markdown)
    return 0
