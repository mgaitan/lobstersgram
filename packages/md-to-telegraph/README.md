# md-to-telegraph

[![PyPI](https://img.shields.io/pypi/v/md-to-telegraph)](https://pypi.org/project/md-to-telegraph/)

Convert Markdown text into [Telegraph](https://telegra.ph/) DOM nodes.

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
