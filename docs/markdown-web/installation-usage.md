# Installation And Usage

## Run Locally

```bash
uv run --package markdown-web markdown-web
```

Open <http://127.0.0.1:8000/>.

## Useful Environment Variables

- `TELEGRAPH_API_TOKEN`: use an existing Telegraph account.
- `REDIS_URL`: enable durable publishing jobs.
- `TELEGRAM_WEB_BOT_TOKEN`: send optional Telegraph notifications.
- `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_PUBLIC_BASE_URL`: enable image uploads.

## Development

```bash
uv run pytest packages/markdown-web/tests
uv run ruff check packages/markdown-web
```
