"""Listens to a Telegram channel/chat with a regular user account (Telethon)
and forwards every new message's text to the given callback.

Requires TELEGRAM_API_ID/API_HASH from https://my.telegram.org - reading a
channel you're a member of needs a logged-in user session, a bot token
cannot do this unless the bot itself is an admin of the channel.
"""
from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Union

from telethon import TelegramClient, events

from config import Config

log = logging.getLogger("telegram_listener")

MessageHandler = Callable[[str], Awaitable[None]]


def resolve_chat_identifier(value: str) -> Union[int, str]:
    """TELEGRAM_CHANNEL can be an @username or a numeric chat ID (private
    channels have no username - get the ID from list_chats.py). Telethon
    needs numeric IDs passed as int, not as a digit string."""
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def build_client(config: Config) -> TelegramClient:
    """A bare, unstarted client - callers must `await client.start()` before
    using it (run_listener no longer does this itself, so the SAME started
    client can also be handed to notifier.Notifier to send fill/daily-summary
    notifications - see main.py's live())."""
    return TelegramClient(config.telegram_session_name, config.telegram_api_id, config.telegram_api_hash)


def _register(client: TelegramClient, chat: Union[int, str], on_message: MessageHandler, label: str) -> None:
    """Wires one chat's NewMessage events to on_message - shared by the
    main channel and the manual-signal chat in run_listener below, so a
    zone/add-to-zone/etc. pasted into either goes through the exact same
    handling."""

    @client.on(events.NewMessage(chats=chat))
    async def _handler(event: events.NewMessage.Event) -> None:
        text = event.raw_text or ""
        if not text.strip():
            return
        log.info("new message (%s): %s", label, text.replace("\n", " | "))
        try:
            await on_message(text)
        except Exception:
            log.exception("error handling message")


async def run_listener(client: TelegramClient, config: Config, on_message: MessageHandler) -> None:
    """Assumes `client` is already started (see build_client) - blocks
    forever listening on config.telegram_channel, plus
    config.telegram_manual_chat when config.manual_signals_enabled (see
    config.py) - lets you paste your own zone signal from your phone into
    a personal chat (defaults to "me", your own Saved Messages) and have
    it go through the exact same parsing/order pipeline as the channel."""
    channel = resolve_chat_identifier(config.telegram_channel)
    _register(client, channel, on_message, "channel")
    log.info("listening on channel %s", channel)

    if config.manual_signals_enabled:
        manual_chat = resolve_chat_identifier(config.telegram_manual_chat)
        if manual_chat == channel:
            log.warning(
                "TELEGRAM_MANUAL_CHAT is the same as TELEGRAM_CHANNEL - not registering a second "
                "listener (would double-handle every channel message)."
            )
        else:
            _register(client, manual_chat, on_message, "manual")
            log.info("also listening for manual zone pastes on %s", config.telegram_manual_chat)

    await client.run_until_disconnected()
