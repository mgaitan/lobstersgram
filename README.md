# Lobstersgram: Lobsters → Telegraph → Telegram (Serverless)

[![CI](https://github.com/mgaitan/lobstersgram/actions/workflows/ci.yml/badge.svg)](https://github.com/mgaitan/lobstersgram/actions/workflows/ci.yml)

Lobstersgram is a fast Telegram client for [lobste.rs](https://lobste.rs). It delivers the hottest Lobsters stories (articles that reached the home page) to the [@lobstersgram](https://t.me/lobstersgram) channel with a clean telegra.ph reading view.

Bot: [@lobstersgram_bot](https://t.me/lobstersgram_bot)
Post: https://mgaitan.github.io/en/posts/lobstersgram-cliente-rapido-lobsters/

The bot publishes to the channel; readers join the channel directly.

Demo:

[![Lobstersgram demo](https://img.youtube.com/vi/wdzIBFYjJ3Y/hqdefault.jpg)](https://youtube.com/shorts/wdzIBFYjJ3Y?si=yMhLPjz7kDGX_1Wl)

---

## How it works

1. A GitHub Actions workflow runs on a schedule (cron).
2. It fetches the Lobste.rs "hottest" RSS feed (home-page articles only).
3. New items are detected via a local `state.json` file.
4. For each new item:
   - The final article URL is resolved.
   - The main content is extracted (Readability-style).
   - A full article page is created on **telegra.ph**.
   - A Telegram channel post is sent with:
     - Title (bold)
     - Source domain
     - Link to the Telegraph page
     - Link to the original article
     - Link to the Lobsters discussion
5. The processed item IDs are stored back into `state.json`, which is committed automatically.

No callbacks, no pagination logic, no bot process running 24/7.

## Reusable packages

This workspace contains reusable packages used by the bot and a small web UI:

- [`markdown-this`](packages/markdown-this/README.md): extracts web pages and supported special URLs as Markdown.
- [`md-to-telegraph`](packages/md-to-telegraph/README.md): converts Markdown into Telegraph DOM nodes.
- [`markdown-web`](packages/markdown-web/README.md): FastAPI service with a web UI, URL endpoints, and bookmarklets for the two tools.

The web app is available at <https://markdown.fastapicloud.dev/>.

The `md-to-telegraph` package also provides an `md-to-telegraph` CLI for
publishing a Markdown file or stdin directly.

Each package has its own version and can be released independently from this workspace.

Run the web service locally with:

```bash
uv run --package markdown-web markdown-web
```

It exposes `/md/{url}` for Markdown and `/t/{url}` for Telegraph publishing.

### Independent releases

Versions live in each package's own `pyproject.toml`. For example, to bump and
release `markdown-this`:

```bash
uv version --package markdown-this --bump patch
uv lock
git commit -am "Release markdown-this $(uv version --package markdown-this --short)"
git tag "markdown-this-v$(uv version --package markdown-this --short)"
git push origin main --tags
```

Create the GitHub release from that tag. The matching publishing workflow
verifies the package version, builds only that package, and publishes it to
PyPI. The reusable packages have separate Trusted Publisher workflows:
`publish-md-to-telegraph.yml` publishes `md-to-telegraph`, and
`publish-markdown-this.yml` publishes `markdown-this`. The `lobstersgram`
application is not published to PyPI yet.

Use the same commands with `md-to-telegraph` as the package name. The tag
format is `<package>-v<version>`.

---

## Why Telegraph?

Telegram bots cannot send hidden data or delegate pagination logic to the client.
Any real “continue reading” flow would require a live bot handling callbacks.

Using **telegra.ph** gives us:

- Fast, clean, mobile-friendly reading
- No hosting or storage to maintain
- Instant article views
- A perfect fit for “read later” from Telegram

---

## Requirements

- Python 3.11+ (used by GitHub Actions)
- A Telegram bot token
- A Telegram channel where the bot can post
- A Telegraph access token
- Optional: `TELEGRAM_DEV_CHAT_ID` to force sends only to your chat during local testing

## Telegram channel

The scheduled workflow publishes each new item to `@lobstersgram`. Readers join
the channel directly, so the bot does not need to maintain a recipient list.

All secrets are stored securely in GitHub Actions.

---

## Setup

### 1. Create a Telegram bot and channel

1. Talk to `@BotFather`
2. Create a new bot
3. Save the bot token (`TELEGRAM_BOT_TOKEN`)

Create a Telegram channel and add the bot as an administrator with the **Post
Messages** permission. Keep channel publishing restricted to administrators.
The current production channel is `@lobstersgram`.

Set the `TELEGRAM_CHANNEL_ID` GitHub Actions secret to `@lobstersgram`. Public
channel usernames can be used directly; private channels require their numeric
chat ID, usually starting with `-100`.

For local development, you can set `TELEGRAM_DEV_CHAT_ID` to force sends only
to your own chat.

---

### 2. Create a Telegraph access token

Run once (locally or in a temporary script):

```python
import requests

r = requests.post(
    "https://api.telegra.ph/createAccount",
    data={
        "short_name": "lobsters2tg",
        "author_name": "Your Name",
        "author_url": "https://lobste.rs/",
    },
)
print(r.json()["result"]["access_token"])
```

Save the resulting token.

---

### 3. Configure GitHub Secrets

In your repository:

**Settings → Secrets and variables → Actions**

Add the following secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `TELEGRAPH_ACCESS_TOKEN`

---

### `state.json`

Local state file used to track already-processed items.
Automatically committed by GitHub Actions.

### `subscribers.json`

Legacy subscribers file containing the `chat_id` values collected by the old
`/start` subscription mechanism. It is retained for the one-time migration
message and is still updated when reaction offsets are synchronized.

### `.github/workflows/lobsters.yml`

Scheduled GitHub Actions workflow that runs the pipeline.

---

## Configuration

Optional environment variables:

- `MAX_ITEMS_PER_RUN` (default: `5`)
- `REQUEST_TIMEOUT` (default: `20` seconds)

These can be set directly in the workflow file.

---

## Running manually

You can trigger the pipeline manually from GitHub:

```
Actions → Lobsters to Telegram → Run workflow
```

Useful for testing or initial bootstrapping.

The scheduled workflow runs `--sync-updates` before publishing. This consumes
Telegram reaction updates so the existing bookmark export keeps working, but it
does not process `/start` or `/unsubscribe` commands.

## Legacy direct-subscription mechanism

Before channel publishing, readers sent `/start` to the bot and the workflow
stored their private or group `chat_id` values in `subscribers.json`. The
`--read-messages` option remains available for reading that legacy state, and
`send-migration-message` sends the prepared migration notice to those stored
chat IDs.

The migration workflow is manual and intentionally separate from the scheduled
publisher. Run it once, after reviewing the message, from:

`Actions → Migrate Telegram subscribers to channel → Run workflow`

---

## Design constraints (by choice)

- ❌ No webhooks
- ❌ No callback queries
- ❌ No pagination inside Telegram
- ❌ No database
- ❌ No server

- ✅ Stateless execution
- ✅ Deterministic behavior
- ✅ Easy to maintain
- ✅ Easy to extend

---

## Possible extensions

- Attach the full article as an HTML or EPUB file
- Add other RSS sources
- Add basic keyword filtering
- Improve Telegraph HTML fidelity
- Mirror articles to a static archive

All without changing the serverless model.

---

## License

MIT
