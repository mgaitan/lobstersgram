# markdown-this Overview

`markdown-this` extracts readable web content and supported special URLs as
Markdown. It is the workspace package that should own content fetching,
metadata extraction, HTML cleanup, and Markdown normalization.

## Goals

- Produce clean Markdown for articles, media pages, source-code pages, and
  local HTML.
- Preserve source metadata such as title, author, canonical URL, publication
  date, image, and page type.
- Recover article text from schema.org JSON-LD when the generic extractor
  selects too little content.
- Keep extraction deterministic and testable with offline fixtures.
- Prefer small, verified provider/rule support over a large unowned rule dump.

## Functionality

- Generic HTML extraction with `readability-lxml`.
- GitHub repository README and Markdown blob extraction through the GitHub API.
- arXiv abstract extraction.
- YouTube metadata, description, and optional transcript extraction.
- Vimeo and Dailymotion media-page extraction through oEmbed.
- Image and figure normalization before Markdown conversion.
