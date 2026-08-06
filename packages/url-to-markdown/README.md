# url-to-markdown

[![PyPI](https://img.shields.io/pypi/v/url-to-markdown)](https://pypi.org/project/url-to-markdown/)

Extract the readable content of a URL and convert it to Markdown. The package
also handles GitHub repositories and Markdown files through the GitHub API,
and arXiv abstract pages through their HTML representation.

## Installation

```bash
uv add url-to-markdown
```

## Usage

```python
from url_to_markdown import extract_main_content

title, markdown, fallback_text, intro = extract_main_content(
    "https://example.com/article"
)
```

`extract_main_content` returns the title, extracted Markdown, plain-text
fallback, and a short introduction suitable for a notification or preview.

The lower-level fetchers and normalization helpers are available from the
package modules when an application needs more control over the pipeline.

## Development

```bash
uv run pytest packages/url-to-markdown/tests
uv run ruff check packages/url-to-markdown
```

## License

MIT
