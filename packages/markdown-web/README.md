# Page to Telegraph

Minimal FastAPI service around [`markdown-this`](../markdown-this/) and
[`md-to-telegraph`](../md-to-telegraph/).

## Run

```bash
uv run --package markdown-web markdown-web
```

Open <http://127.0.0.1:8000/>. Set `TELEGRAPH_API_TOKEN` to use an existing
Telegraph account. When it is absent, the service creates one lazily and keeps
the token in memory for the lifetime of the process. Set `REDIS_URL` to enable
optional durable publishing jobs and install them with
`pip install "markdown-web[jobs]"`; synchronous routes and the base installation
do not require Redis.

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

To publish a brief with linked article pages, place exact lowercase card markers
in the Markdown:

```markdown
# Weekend brief

Editorial context.

![card](https://example.com/article)
```

`POST /t` publishes each marked source to Telegraph, replaces the marker with a
linked image, title, introduction, and Telegraph link, and adds navigation back
to the brief plus the previous and next curated articles. Marker order controls
navigation, and a repeated URL is published once within the brief.

### Optional jobs

For a long brief, `POST /t/jobs` accepts the same Markdown JSON body and returns
HTTP `202` with a job `id`, `status_url`, and `run_url`. Call `POST <run_url>`
until it returns HTTP `200` with `status: completed` and the final Telegraph
`url`. Each call advances one bounded publishing stage. `GET <status_url>` reads
progress without changing it.

Job state and locks are stored in Redis for 48 hours. Sending the same Markdown
and metadata during that period returns the same job. A failed stage returns
HTTP `422` with its error and source URL and can be retried by posting to the
same `run_url`. Jobs use the service's configured Telegraph account and reject
client access tokens. When `REDIS_URL` is absent, only the job endpoints return
HTTP `503`; `POST /t` continues to work synchronously.

```bash
curl -X POST http://127.0.0.1:8000/t/jobs \
  -H 'content-type: application/json' \
  -d '{"markdown":"# Weekend brief\n\n![card](https://example.com/article)"}'
```

Agents can read `/llms.txt` for the endpoint contract, accepted YAML front
matter, and examples. The machine-readable contract is FastAPI's existing
OpenAPI document at `/openapi.json`; there is no separate `openschema.json`.

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
