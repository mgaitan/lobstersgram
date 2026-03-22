"""Data models and exceptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    link: str
    discussion_link: str
    source: str
    tags: list[str]


class TelegramAPIError(RuntimeError):
    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegram API error")
        self.data = data


class TelegraphAPIError(RuntimeError):
    def __init__(self, data: dict[str, object]) -> None:
        super().__init__("Telegraph API error")
        self.data = data


class ContentDownloadError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Failed to download content")
