# markdown-web

## Purpose

This package is the FastAPI service at https://markdown.fastapicloud.dev/. It
extracts URLs or HTML with `markdown-this`, publishes Markdown to Telegraph with
`md-to-telegraph`, and optionally advances long briefs through Redis jobs.

## Important boundaries

- Keep HTTP routes and request parsing in `src/markdown_web/app.py`.
- Keep publication orchestration and content preparation in `service.py`.
- Keep Redis job state and stage advancement in `jobs.py`.
- Keep Telegram delivery in `telegram.py`. It sends only the Telegraph URL and
  must remain best effort so a Telegram outage does not turn a successful
  Telegraph publication into a duplicate on retry.
- Do not commit `.env` or `.fastapicloud/`; both contain local credentials or
  deployment identifiers.

## Telegram notifications

Markdown can start with YAML front matter such as:

```yaml
---
title: An article
notify_telegram: 123456789, -1001234567890
---
```

`notify_telegram` is a comma-separated list. One `sendMessage` request is made
per unique recipient, with the published Telegraph URL as the complete message
text. The bot token comes from `TELEGRAM_WEB_BOT_TOKEN`. A missing token or a
Telegram API failure is logged and does not fail the Telegraph request. Durable
jobs persist whether their final URL notification was attempted.

The private recipient must first open
https://t.me/MarkdownTelegraphBot and send `/start`. In a group, add the bot and
give it permission to send messages. In a channel, add it as an administrator
with the `can_post_messages` right.

## Local checks

Run from the repository root:

```bash
uv run pytest packages/markdown-web/tests
uv run ruff check packages/markdown-web
uv run ruff format --check packages/markdown-web
```

The full workspace checks are `uv run pytest -q`, `uv run ruff check .`, and
`uv build --all-packages`.

## FastAPI Cloud deployment

The package is linked to FastAPI Cloud through `.fastapicloud/cloud.json`.
Deploy from `packages/markdown-web/` with:

```bash
uv run fastapi cloud deploy .
```

Set the production secret through the CLI, never in git:

```bash
printf '%s' "$TELEGRAM_WEB_BOT_TOKEN" |
  uv run fastapi cloud env set TELEGRAM_WEB_BOT_TOKEN --value-stdin --secret
```

After changing a cloud environment variable, deploy again if the platform does
not automatically restart the app. Check the public URL and deployment logs
after each deploy.
