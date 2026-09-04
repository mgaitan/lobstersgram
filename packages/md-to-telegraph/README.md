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

For content that may exceed Telegraph's page size, use `create_pages`. It
splits Markdown between complete blocks (without cutting paragraphs, fenced
code, or other Markdown constructs), creates linked pages with previous/next
navigation, and returns all URLs plus their Markdown chunks:

```python
from md_to_telegraph import create_pages

pages = create_pages(access_token="telegraph-token", title="A long article", content_markdown=content_markdown)
first_url = pages.urls[0]
```

`create_page` reads YAML front matter from `content_markdown`. When these
arguments are omitted, it uses `title`, `author`, and `url` from the header;
explicit arguments always take precedence. The `date` field is preserved as
metadata but Telegraph has no native page-date field.
When an author is not available, the source URL's domain is used as the author
name, while the complete source URL is sent as `author_url`.

When the front matter declares a non-document page type such as `website`,
`home`, `collection`, or `search`, `create_page` refuses to publish it.
This prevents accidentally turning site home pages and listings into
Telegraph articles.

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

To create only a token, use the `create-account` subcommand. It prints a shell
assignment and does not publish a page:

```bash
md-to-telegraph create-account --short-name lobstersgram
export $(md-to-telegraph create-account --short-name lobstersgram)
```

The output can also be appended to a shell startup file:

```bash
echo "export $(md-to-telegraph create-account --short-name lobstersgram)" >> ~/.bashrc
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
