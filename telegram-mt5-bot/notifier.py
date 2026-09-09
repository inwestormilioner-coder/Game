"""Sends Telegram notifications (fill screenshots, daily summary) using the
SAME logged-in Telethon session that reads the signal channel (see
telegram_listener.py) - no separate Telegram bot/token needed.
TELEGRAM_NOTIFY_CHAT picks the destination: "me" (default) sends to your
own Saved Messages, or set it to a group/channel @username or numeric id to
post there instead.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from telethon import TelegramClient

from telegram_listener import resolve_chat_identifier

__all__ = ["Notifier", "resolve_chat_identifier"]


class Notifier:
    def __init__(self, client: TelegramClient, chat: Union[int, str]):
        self._client = client
        self._chat = chat

    async def send_text(self, text: str) -> None:
        await self._client.send_message(self._chat, text)

    async def send_photo(self, path: Path, caption: str) -> None:
        await self._client.send_file(self._chat, str(path), caption=caption)
