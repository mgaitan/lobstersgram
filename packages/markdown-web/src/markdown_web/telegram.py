"""Best-effort Telegram notifications for published Telegraph pages."""

from __future__ import annotations

import logging
import os

import requests

TELEGRAM_API_URL = "https://api.telegram.org"
TELEGRAM_REQUEST_TIMEOUT = 20
logger = logging.getLogger(__name__)


def _chat_ids(value: str) -> tuple[str, ...]:
    """Return non-empty comma-separated Telegram chat IDs in input order."""
    return tuple(dict.fromkeys(chat_id.strip() for chat_id in value.split(",") if chat_id.strip()))


def send_telegram_notifications(url: str, recipients: str) -> None:
    """Send only the published URL to each requested chat, without failing publication."""
    if not recipients:
        return
    if not (token := os.getenv("TELEGRAM_WEB_BOT_TOKEN")):
        logger.warning("Telegram notification skipped: TELEGRAM_WEB_BOT_TOKEN is not configured")
        return

    for chat_id in _chat_ids(recipients):
        try:
            response = requests.post(
                f"{TELEGRAM_API_URL}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": url},
                timeout=TELEGRAM_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("ok"):
                logger.warning("Telegram notification failed chat_id=%s: unsuccessful API response", chat_id)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Telegram notification failed chat_id=%s error=%s", chat_id, exc)
