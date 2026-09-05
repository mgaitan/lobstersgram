# markdown-web Overview

`markdown-web` is a FastAPI service around `markdown-this` and
`md-to-telegraph`.

## Goals

- Provide URL-to-Markdown and URL-to-Telegraph HTTP endpoints.
- Offer a small browser UI and bookmarklets for pages that need client-side
  HTML capture.
- Support document and image uploads without moving those concerns into the
  reusable packages.

## Functionality

- `/md/{url}` and `/t/{url}` endpoints.
- POST endpoints for Markdown, raw HTML, URLs, and uploaded documents.
- Telegraph job support with Redis.
- Bookmarklets for rendered-page capture.
- Image upload, resize, WebP conversion, and R2-backed public URLs.
