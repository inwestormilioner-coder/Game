"""Listens to a Telegram channel/chat with a regular user account (Telethon)
and forwards every new message's text to the given callback.

Requires TELEGRAM_API_ID/API_HASH from https://my.telegram.org - reading a
channel you're a member of needs a logged-in user session, a bot token
cannot do this unless the bot itself is an admin of the channel.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telethon import TelegramClient, events

from config import Config

log = logging.getLogger("telegram_listener")

MessageHandler = Callable[[str], Awaitable[None]]


async def run_listener(config: Config, on_message: MessageHandler) -> None:
    client = TelegramClient(config.telegram_session_name, config.telegram_api_id, config.telegram_api_hash)

    @client.on(events.NewMessage(chats=config.telegram_channel))
    async def _handler(event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        if not text.strip():
            return
        log.info("new message: %s", text.replace("\n", " | "))
        try:
            await on_message(text)
        except Exception:
            log.exception("error handling message")

    await client.start()
    log.info("listening on channel %s", config.telegram_channel)
    await client.run_until_disconnected()
