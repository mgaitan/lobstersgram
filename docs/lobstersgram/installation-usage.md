# Lobstersgram Installation And Usage

## Requirements

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `TELEGRAPH_ACCESS_TOKEN`
- Optional `TELEGRAM_DEV_CHAT_ID` for local test sends.

## CLI

```bash
uv run lobstersgram --help
```

## GitHub Actions

The scheduled workflow lives in `.github/workflows/lobsters.yml`. It runs the
publisher, commits updated runtime state, and keeps the app serverless.
