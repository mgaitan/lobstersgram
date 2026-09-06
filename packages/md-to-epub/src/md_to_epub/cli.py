"""Command-line interface for building EPUB books."""

from __future__ import annotations

import argparse
from pathlib import Path

from md_to_epub import Book, Chapter, write_epub


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an EPUB 3 book from Markdown files")
    parser.add_argument("files", nargs="+", type=Path, help="Markdown chapters in book order")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output EPUB path")
    parser.add_argument("--title", required=True, help="Book title")
    parser.add_argument("--author", default="", help="Book author")
    parser.add_argument("--language", default="es", help="Book language")
    args = parser.parse_args()
    chapters = tuple(
        Chapter(title=path.stem.replace("-", " ").title(), markdown=path.read_text(encoding="utf-8"))
        for path in args.files
    )
    write_epub(Book(title=args.title, author=args.author, language=args.language, chapters=chapters), args.output)
