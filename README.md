# Lobstergram: Lobsters → Telegraph → Telegram (Serverless)

Lobstergram is a fast Telegram client for [lobste.rs](https://lobste.rs). It delivers new Lobsters stories right into Telegram with a clean telegra.ph reading view.

Bot: [@lobstersgram_bot](https://t.me/lobstersgram_bot)

Commands:
- `/start` to subscribe
- `/unsubscribe` to stop receiving posts

Demo:

[![Lobstergram demo](https://img.youtube.com/vi/wdzIBFYjJ3Y/hqdefault.jpg)](https://youtube.com/shorts/wdzIBFYjJ3Y?si=yMhLPjz7kDGX_1Wl)

---

## How it works

1. A GitHub Actions workflow runs on a schedule (cron).
2. It fetches the Lobste.rs RSS feed.
3. New items are detected via a local `state.json` file.
4. For each new item:
   - The final article URL is resolved.
   - The main content is extracted (Readability-style).
   - A full article page is created on **telegra.ph**.
   - A Telegram message is sent with:
     - Title (bold)
     - Source domain
     - Link to the Telegraph page
     - Link to the original article
     - Link to the Lobsters discussion
5. The processed item IDs are stored back into `state.json`, which is committed automatically.

No callbacks, no pagination logic, no bot process running 24/7.

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
- One or more Telegram subscribers (see below)
- A Telegraph access token
- Optional: `TELEGRAM_DEV_CHAT_ID` to force sends only to your chat during local testing

## Subscribers

Users subscribe by sending `/start` to the bot. Run the workflow in `--read-messages`
mode to fetch pending updates and store subscribers in `subscribers.json`. The normal
mode sends each post to every subscriber in that file.

All secrets are stored securely in GitHub Actions.

---

## Setup

### 1. Create a Telegram bot

1. Talk to `@BotFather`
2. Create a new bot
3. Save the bot token (`TELEGRAM_BOT_TOKEN`)

To register subscribers:
- Send `/start` to the bot from the Telegram account or group you want to receive posts.
- Run the workflow once (or run `uv run python main.py --read-messages`) to record the
  `chat_id` values into `subscribers.json`.

For local development, you can set `TELEGRAM_DEV_CHAT_ID` to force all sends
to your own chat without touching `subscribers.json`.

To stop receiving posts, send `/unsubscribe` to the bot and run `--read-messages`
again to remove the chat from `subscribers.json`.

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
- `TELEGRAPH_ACCESS_TOKEN`

---

### `state.json`

Local state file used to track already-processed items.
Automatically committed by GitHub Actions.

### `subscribers.json`

Local subscribers file used to store `chat_id` values from `/start`.
Automatically committed by GitHub Actions when it changes.

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
