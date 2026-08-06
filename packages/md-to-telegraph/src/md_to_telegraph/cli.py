"""Command-line interface for publishing Markdown to Telegraph."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from md_to_telegraph.markdown import extract_leading_title
from md_to_telegraph.metadata import split_front_matter
from md_to_telegraph.telegraph import (
    TelegraphAPIError,
    TelegraphTitleError,
    TelegraphTokenError,
    create_account,
    create_page,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish Markdown content to Telegraph",
        epilog="Use 'create-account' to print a TELEGRAPH_API_TOKEN assignment.",
    )
    parser.add_argument("path", nargs="?", type=Path, help="Markdown file; read stdin when omitted")
    parser.add_argument("--title", help="Page title; overrides YAML front matter and Markdown headings")
    parser.add_argument("--fallback-text", default="", help="Plain-text fallback when Markdown has no nodes")
    parser.add_argument("--source-url", default="", help="Source URL shown as the author link")
    parser.add_argument("--author-name", default="", help="Author name shown below the page title")
    parser.add_argument("--access-token", help="Telegraph access token (or TELEGRAPH_API_TOKEN)")
    parser.add_argument("--create-account", action="store_true", help="Create a Telegraph account for this page")
    parser.add_argument("--short-name", help="Short name for a newly created Telegraph account")
    parser.add_argument("--request-timeout", type=int, default=20)
    parser.add_argument("--retry-attempts", type=int, default=None)
    parser.add_argument("--no-warm-cache", action="store_true")
    return parser


def _account_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Telegraph account and print its access token")
    parser.add_argument("--short-name", default="md-to-telegraph", help="Telegraph account short name")
    parser.add_argument("--author-name", default="", help="Account author name")
    parser.add_argument("--author-url", default="", help="Account author URL")
    parser.add_argument("--request-timeout", type=int, default=20)
    parser.add_argument("--retry-attempts", type=int, default=None)
    return parser


def _create_account(argv: list[str]) -> int:
    parser = _account_parser()
    args = parser.parse_args(argv)
    try:
        token = create_account(
            short_name=args.short_name,
            author_name=args.author_name,
            author_url=args.author_url,
            request_timeout=args.request_timeout,
            retry_attempts=args.retry_attempts,
        )
    except (TelegraphAPIError, OSError) as exc:
        parser.error(str(exc))

    print(f"TELEGRAPH_API_TOKEN={token}")
    return 0


def _read_markdown(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    command_line = sys.argv[1:] if argv is None else argv
    if command_line and command_line[0] == "create-account":
        return _create_account(command_line[1:])

    parser = _parser()
    args = parser.parse_args(command_line)

    try:
        markdown = _read_markdown(args.path)
    except OSError as exc:
        parser.error(str(exc))

    metadata, markdown_body = split_front_matter(markdown)
    title = args.title or metadata.get("title")
    title = title or (args.path.stem if args.path else extract_leading_title(markdown_body))
    if not title:
        parser.error("--title is required when no YAML title or first Markdown heading is available")

    token = args.access_token or os.getenv("TELEGRAPH_API_TOKEN")
    try:
        if args.create_account:
            short_name = (args.short_name or title)[:32] or "md-to-telegraph"
            token = create_account(
                short_name=short_name,
                author_name=args.author_name,
                author_url=args.source_url,
                request_timeout=args.request_timeout,
                retry_attempts=args.retry_attempts,
            )
        url = create_page(
            title=title,
            content_markdown=markdown,
            fallback_text=args.fallback_text,
            source_url=args.source_url,
            author_name=args.author_name,
            access_token=token,
            request_timeout=args.request_timeout,
            retry_attempts=args.retry_attempts,
            warm_cache=not args.no_warm_cache,
        )
    except (TelegraphAPIError, TelegraphTitleError, TelegraphTokenError, OSError) as exc:
        parser.error(str(exc))

    print(url)
    return 0
