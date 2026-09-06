# Installation And Usage

## Installation

```bash
uv add md-to-telegraph
```

## Python API

```python
from md_to_telegraph import md_to_telegraph

nodes = md_to_telegraph("# Hello\n\nThis is **bold** text.")
```

```python
from md_to_telegraph import create_page

url = create_page(
    access_token="telegraph-token",
    title="An article",
    content_markdown=content_markdown,
    fallback_text=fallback_text,
    source_url="https://example.com/article",
)
```

## CLI

```bash
uvx md-to-telegraph article.md --access-token "$TELEGRAPH_API_TOKEN"
cat article.md | uvx md-to-telegraph --title "An article"
```
