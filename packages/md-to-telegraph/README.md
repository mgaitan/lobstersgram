# md-to-telegraph

[![PyPI](https://img.shields.io/pypi/v/md-to-telegraph)](https://pypi.org/project/md-to-telegraph/)

Convert Markdown text into [Telegraph](https://telegra.ph/) DOM nodes and
publish pages through the Telegraph API.

## Overview

`md-to-telegraph` transforms a Markdown string into a list of Telegraph-compatible DOM node dicts, suitable for use with the [Telegraph API](https://telegra.ph/api#Node).

Telegraph nodes follow this structure:

```json
{
  "tag": "p",
  "attrs": {"href": "..."},
  "children": ["text", {"tag": "strong", "children": ["bold"]}]
}
```

## Installation

```bash
uv add md-to-telegraph
```

## Usage

```python
from md_to_telegraph import md_to_telegraph

nodes = md_to_telegraph("# Hello\n\nThis is **bold** text.")
# [
#   {"tag": "h3", "children": ["Hello"]},
#   {"tag": "p", "children": ["This is ", {"tag": "strong", "children": ["bold"]}, " text."]}
# ]
```

For extracted content that may need a plain-text fallback, use
`content_to_telegraph`:

```python
from md_to_telegraph import content_to_telegraph

nodes = content_to_telegraph(content_markdown, fallback_text)
```

To create a page directly, use `create_page`. The default performs one API
request; pass `retry_attempts` to retry transient failures:

```python
from md_to_telegraph import create_page

url = create_page(
    access_token="telegraph-token",
    title="An article",
    content_markdown=content_markdown,
    fallback_text=fallback_text,
    source_url="https://example.com/article",
    retry_attempts=3,
)
```

The same operation is available as a command-line tool. A file uses its stem
as the default title; stdin uses its first Markdown heading, or accepts an
explicit `--title`:

```bash
md-to-telegraph article.md --access-token "$TELEGRAPH_API_TOKEN"
cat article.md | md-to-telegraph --title "An article"
```

The token can be passed with `--access-token` or read from
`TELEGRAPH_API_TOKEN`. To create a new Telegraph account explicitly and use
its token for the page, add `--create-account` (optionally with `--short-name`).
The account creation uses Telegraph's `createAccount` method.

## Markdown features supported

| Markdown element       | Telegraph output           |
|------------------------|----------------------------|
| `# Heading 1`          | `<h3>`                     |
| `## Heading 2`         | `<h4>`                     |
| `### Heading 3+`       | `<p><strong>…</strong></p>`|
| `**bold**`             | `<strong>`                 |
| `*italic*`             | `<em>`                     |
| `` `code` ``           | `<code>`                   |
| `~~strike~~`           | `<del>`                    |
| `[text](url)`          | `<a href="…">`             |
| `<url>`                | `<a href="…">`             |
| `![alt](url)`          | `<img src="…">`            |
| ` ```lang\ncode\n``` ` | `<pre><code>`              |
| `> quote`              | `<blockquote>`             |
| `- item` / `1. item`   | `<ul>` / `<ol>`            |
| `---`                  | `<hr>`                     |
| hard line break (`  `) | `<br>`                     |
| soft line break        | space                      |

## Development

```bash
uv run pytest
```

## License

MIT
