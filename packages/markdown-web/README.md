# Page to Telegraph

Minimal FastAPI service around [`markdown-this`](../markdown-this/) and
[`md-to-telegraph`](../md-to-telegraph/).

## Run

```bash
uv run --package markdown-web markdown-web
```

Open <http://127.0.0.1:8000/>. Set `TELEGRAPH_API_TOKEN` to use an existing
Telegraph account. When it is absent, the service creates one lazily and keeps
the token in memory for the lifetime of the process.

## HTTP API

The URL is a path, in the style of `r.jina.ai`:

```bash
curl http://127.0.0.1:8000/md/https://example.com/article
curl -L http://127.0.0.1:8000/t/https://example.com/article
```

GET `/t/<url>` reuses the Telegraph page already created for that source URL
by this running service. POST `/t` always publishes the supplied content.
GET `/t/published/` lists the pages published by the configured Telegraph account.
The original source is shown when Telegraph has it in the page's author URL.

The target URL should be URL-encoded when it contains characters that have a
meaning to the web server. POST endpoints accept JSON with a URL, raw HTML, or
Markdown:

```bash
curl -X POST http://127.0.0.1:8000/md \
  -H 'content-type: application/json' \
  -d '{"html":"<h1>Hello</h1><p>Body</p>","metadata":{"url":"https://example.com"}}'

curl -X POST http://127.0.0.1:8000/t \
  -H 'content-type: application/json' \
  -d '{"markdown":"# Hello\n\nBody"}'
```

Raw HTML can also be posted as `text/html`. Optional metadata is supplied with
`X-Source-URL`, `X-Title`, `X-Author-Name`, `X-Published-Date`, and `X-Image-URL`.
An `access_token` JSON field or `Authorization` header can select a Telegraph
account; otherwise the server token is used.

## Bookmarklets

Visit `/bookmarklet/` to get two permanent bookmarklets. Drag either link to
your browser's bookmarks bar, then click it while reading a page. They capture
the current document HTML in the browser, so they also work with pages rendered
by JavaScript or pages the server cannot access itself. Publishing uses the
server's `TELEGRAPH_API_TOKEN` (or its automatically created account); the raw
token is never included in the bookmarklet.

## Development

```bash
uv run pytest packages/markdown-web/tests
uv run ruff check packages/markdown-web
```

MIT
