# markdown-this

[![PyPI](https://img.shields.io/pypi/v/markdown-this)](https://pypi.org/project/markdown-this/)

Extract the readable content of a URL and convert it to Markdown. The package
also handles GitHub repositories and Markdown files through the GitHub API,
and arXiv abstract pages through their HTML representation.

## Installation

```bash
uv add markdown-this
```

## Usage

```python
from markdown_this import extract_main_content

title, markdown, fallback_text, intro = extract_main_content(
    "https://example.com/article"
)
```

The source can also be a local HTML file (`Path` or path string) or raw HTML:

```python
from pathlib import Path
from markdown_this import extract_main_content

title, markdown, fallback_text, intro = extract_main_content(Path("article.html"))
title, markdown, fallback_text, intro = extract_main_content("<html><p>...</p></html>")
```

`extract_main_content` returns the title, extracted Markdown, plain-text
fallback, and a short introduction suitable for a notification or preview.
The Markdown value starts with YAML front matter containing the metadata that
was found, such as `title`, `author`, `url`, `date`, and the declared page
`type` (`article`, `website`, `home`, and so on).

For example:

```markdown
---
title: An article
author: An author
url: https://example.com/article
date: 2026-08-06
---

Article content.
```

The package also installs a `markdown-this` command:

```bash
markdown-this https://example.com/article
markdown-this article.html
cat article.html | markdown-this -
```

The command writes the extracted Markdown to stdout. Its input may be a URL,
an existing HTML path, or HTML read from stdin.

The lower-level fetchers and normalization helpers are available from the
package modules when an application needs more control over the pipeline.

## Development

```bash
uv run pytest packages/markdown-this/tests
uv run ruff check packages/markdown-this
```

## License

MIT
