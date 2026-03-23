"""Telegram API interactions and subscriber management."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import requests

from lobstergram import config
from lobstergram.state import load_message_map, load_subscribers, save_subscribers, sync_bookmarks


class TelegramAPIError(RuntimeError):
    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegram API error")
        self.data = data


def telegram_get_updates(offset: int) -> list[dict[str, object]]:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 0, "offset": offset, "allowed_updates": json.dumps(["message", "message_reaction"])}
    r = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise TelegramAPIError(data)
    return data.get("result", [])


def telegram_send_message(chat_id: str | int, text_html: str, disable_preview: bool = False) -> int | None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    config.log("debug", f"telegram_send_message chat_id={chat_id} preview_disabled={disable_preview}")
    for attempt in range(1, config.TELEGRAM_RETRY_ATTEMPTS + 1):
        r = requests.post(url, data=payload, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == config._HTTP_TOO_MANY_REQUESTS:
            try:
                retry_after = (r.json().get("parameters") or {}).get("retry_after", 5)
            except Exception:  # noqa: BLE001
                retry_after = 5
            config.log(
                "warn",
                f"telegram rate limited retry_after={retry_after}s attempt={attempt}/{config.TELEGRAM_RETRY_ATTEMPTS}",
            )
            if attempt < config.TELEGRAM_RETRY_ATTEMPTS:
                time.sleep(float(retry_after))
                continue
        elif r.status_code >= config._HTTP_SERVER_ERROR_MIN:
            config.log(
                "warn",
                f"telegram server error status={r.status_code} attempt={attempt}/{config.TELEGRAM_RETRY_ATTEMPTS}",
            )
            if attempt < config.TELEGRAM_RETRY_ATTEMPTS:
                time.sleep(min(2.0**attempt, 30.0))
                continue
        r.raise_for_status()
        result = r.json().get("result") or {}
        message_id = result.get("message_id")
        return int(message_id) if message_id is not None else None
    msg = "telegram_send_message exhausted all attempts without raising"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover


def resolve_recipient_chat_ids(subscribers: list[dict[str, object]]) -> list[str | int]:
    if config.TELEGRAM_DEV_CHAT_ID:
        return [config.TELEGRAM_DEV_CHAT_ID]
    return [sub["chat_id"] for sub in subscribers]


def send_to_recipients(recipients: list[str | int], message: str, disable_preview: bool = True) -> dict[str | int, int]:
    sent: dict[str | int, int] = {}
    for i, chat_id in enumerate(recipients):
        try:
            message_id = telegram_send_message(chat_id, message, disable_preview=disable_preview)
            if message_id is not None:
                sent[chat_id] = message_id
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == config._HTTP_FORBIDDEN:
                config.log("warn", f"send_to_recipients chat_id={chat_id} blocked or forbidden, skipping")
            else:
                config.log("error", f"send_to_recipients chat_id={chat_id} err={type(exc).__name__}: {exc}")
        if i < len(recipients) - 1:
            time.sleep(config.INTER_MESSAGE_DELAY)
    return sent


def _extract_reaction_row(
    reaction: dict[str, object],
    msg_map: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Build a bookmark row from a ``message_reaction`` update payload.

    Returns ``None`` only when the message isn't tracked or lacks actor data.
    An empty ``emojis`` value signals a removal/non-emoji update so callers can
    remove any existing bookmark row for that subscriber/article pair.
    """
    new_reaction = reaction.get("new_reaction") or []
    emojis = " ".join(
        str(r.get("emoji", ""))
        for r in new_reaction  # type: ignore[union-attr]
        if isinstance(r, dict) and r.get("type") == "emoji" and r.get("emoji")
    )

    chat_id = (reaction.get("chat") or {}).get("id")  # type: ignore[union-attr]
    message_id = reaction.get("message_id")
    if not chat_id or not message_id:
        return None

    key = f"{chat_id}:{message_id}"
    article_links = msg_map.get(key)
    if not article_links:
        config.log("debug", f"reaction for untracked message key={key}")
        return None

    user: dict[str, object] = reaction.get("user") or {}  # type: ignore[assignment]
    actor_chat: dict[str, object] = reaction.get("actor_chat") or {}  # type: ignore[assignment]
    if user:
        user_id = str(user.get("id") or "")
        username = str(user.get("username") or user.get("first_name") or user_id)
    else:
        user_id = str(actor_chat.get("id") or "")
        username = str(actor_chat.get("title") or actor_chat.get("username") or user_id)
    if not user_id:
        return None

    return {
        "telegraph_link": article_links.get("telegraph_link", ""),
        "article_link": article_links.get("article_link", ""),
        "discussion_link": article_links.get("discussion_link", ""),
        "username": username,
        "user_id": user_id,
        "emojis": emojis,
        "reacted_at": datetime.now(tz=UTC).isoformat(),
    }


def _handle_command_update(
    update: dict[str, object],
    subscribers: dict[object, dict[str, object]],
) -> tuple[int, int]:
    """Process a single command message update (/start or /unsubscribe).

    Returns ``(new_count, removed_count)`` for the caller to accumulate.
    """
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if text.startswith("/unsubscribe"):
        if chat_id in subscribers:
            subscribers.pop(chat_id, None)
            telegram_send_message(
                chat_id,
                "✅ Unsubscribed. You will no longer receive posts.",
                disable_preview=True,
            )
            return 0, 1
        return 0, 0

    if not text.startswith("/start") or not chat_id or chat_id in subscribers:
        return 0, 0

    subscribers[chat_id] = {
        "chat_id": chat_id,
        "type": chat.get("type"),
        "username": chat.get("username"),
        "first_name": chat.get("first_name"),
        "last_name": chat.get("last_name"),
    }
    telegram_send_message(
        chat_id,
        "✅ Subscribed. You'll receive new posts when they're published.",
        disable_preview=True,
    )
    return 1, 0


def read_new_subscribers() -> int:
    state = load_subscribers()
    last_update_id = int(state.get("last_update_id") or 0)
    offset = last_update_id + 1 if last_update_id else 0
    updates = telegram_get_updates(offset)
    if not updates:
        config.log("info", "read_messages no updates")
        return 0

    subscribers = {s.get("chat_id"): s for s in state.get("subscribers", [])}
    max_update_id = last_update_id
    new_count = 0
    removed_count = 0
    reaction_rows: list[dict[str, str]] = []
    msg_map = load_message_map()
    for update in updates:
        update_id = int(update.get("update_id") or 0)
        max_update_id = max(max_update_id, update_id)

        # Handle emoji reactions — map them to bookmarks.
        reaction = update.get("message_reaction")
        if reaction:
            row = _extract_reaction_row(reaction, msg_map)  # type: ignore[arg-type]
            if row:
                reaction_rows.append(row)
            continue

        added, removed = _handle_command_update(update, subscribers)
        new_count += added
        removed_count += removed

    synced_reactions = sync_bookmarks(reaction_rows)

    state["subscribers"] = list(subscribers.values())
    state["last_update_id"] = max_update_id
    save_subscribers(state)
    config.log(
        "info",
        f"read_messages new_subscribers={new_count} removed_subscribers={removed_count} reactions={synced_reactions}",
    )
    return new_count
