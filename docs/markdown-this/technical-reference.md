# markdown-this Technical Reference

## Current Pipeline

`extract_main_content` returns `(title, markdown, fallback_text, intro)`.

For HTTP URLs, the current order is:

1. GitHub Markdown blob.
2. GitHub repository README.
3. arXiv abstract.
4. Pagina/12 Fusion article data.
5. Vimeo/Dailymotion oEmbed media.
6. YouTube video.
7. Generic HTML fetch plus Readability extraction.

For local paths and raw HTML, only the generic HTML path runs.

## Main Modules

- `markdown_this.extractor`: public pipeline orchestration.
- `markdown_this.fetchers`: HTTP fetchers and special URL handlers.
- `markdown_this.html`: HTML cleanup before Markdown conversion.
- `markdown_this.markdown`: Markdown normalization and preview text helpers.
- `markdown_this.metadata`: YAML front matter and HTML metadata extraction.

## Testing Notes

The root pytest configuration enforces 100% coverage for `markdown-this` and
`md-to-telegraph`. New extraction behavior should add narrow offline fixtures
before using live URLs.
