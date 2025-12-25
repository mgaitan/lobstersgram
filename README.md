# Lobstergram: Lobsters → Telegraph → Telegram (Serverless)



Lobstergram is a telegram bot that send (me) the articles from [lobste.rs](https://lobste.rs). 

It implements a **serverless content delivery pipeline** that:

- Reads new items from the **Lobste.rs RSS feed**
- Extracts the **full article content** using generic scraping
- Publishes a clean reading view on **telegra.ph**
- Sends a formatted message to **Telegram** with the Telegraph link
- Runs entirely on **GitHub Actions** (no server, no webhook, no long-running bot)

The goal is to comfortably read Lobsters articles from Telegram, without relying on truncated RSS content or maintaining any infrastructure.

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

To get your chat ID:
- Send any message to the bot
- Open:
  ```
  https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
  ```
- Extract `chat.id`

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
- `TELEGRAM_CHAT_ID`
- `TELEGRAPH_ACCESS_TOKEN`

---

### `state.json`

Local state file used to track already-processed items.
Automatically committed by GitHub Actions.

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
