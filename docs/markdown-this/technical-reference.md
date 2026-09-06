# markdown-this Technical Reference

## Current Pipeline

`extract_main_content` returns `(title, markdown, fallback_text, intro)`.

URL acquisition can use the existing GitHub, arXiv and YouTube integrations
or the shared oEmbed client. Otherwise it downloads HTML once.

Downloaded HTML, local files and supplied HTML share this pipeline:

1. Read metadata and the source URL.
2. Extract embedded Arc Fusion article data when present, on any hostname.
3. Select a body using a declarative domain rule when one matches.
4. Use Readability, with schema.org article text as a fallback for short or
   missing content. Nested nodes and multiple declared types are supported.
5. Normalize images, figures and relative links and remove structural chrome.
6. Convert to Markdown, add front matter and derive preview text.

Pass `source_url=` with supplied HTML to resolve its relative links. The web
service forwards the URL from request metadata for bookmarklet extraction.

Rules in `markdown_this.rules` declare hostnames, ordered body selectors and
selectors to strip inside the body. The first nonempty body wins; nested
selectors do not duplicate content. Each default rule needs an offline fixture.
Unmarked `aside` elements are preserved because they may contain article notes.

## Main Modules

- `markdown_this.extractor`: public pipeline orchestration.
- `markdown_this.fetchers`: HTTP fetchers and special URL handlers.
- `markdown_this.html`: HTML cleanup before Markdown conversion.
- `markdown_this.markdown`: Markdown normalization and preview text helpers.
- `markdown_this.metadata`: YAML front matter and HTML metadata extraction.
- `markdown_this.structured`: embedded article formats, independent of hostnames.
- `markdown_this.rules`: declarative domain selectors for known high-value
  sites.

## Testing Notes

The root pytest configuration enforces 100% coverage for `markdown-this` and
`md-to-telegraph`. New extraction behavior should add narrow offline fixtures
before using live URLs.
