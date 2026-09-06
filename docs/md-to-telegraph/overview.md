# md-to-telegraph Overview

`md-to-telegraph` converts Markdown into Telegraph-compatible DOM nodes and can
publish those nodes through the Telegraph API.

## Goals

- Keep Markdown-to-Telegraph conversion reusable outside the Telegram and web
  apps.
- Preserve supported Markdown semantics within Telegraph's smaller node model.
- Refuse non-document page types before publishing.

## Functionality

- Markdown block and inline conversion.
- YAML front matter support for title, author, URL, date, image, and type.
- Single-page and multi-page Telegraph publishing.
- CLI publishing from files or stdin.
