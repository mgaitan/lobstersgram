# Installation And Usage

Install the package with uv:

```bash
uv add md-to-epub
```

Build a book from Markdown files with the CLI:

```bash
md-to-epub --title "My book" --author "An author" -o my-book.epub chapter-01.md chapter-02.md
```

The web service exposes the same workflow through `POST /epub` and accepts the
JSON source format used by `POST /md`.
