"""One-off helper to find a private channel's numeric ID.

A private channel has no @username, so TELEGRAM_CHANNEL in .env needs its
ID instead. This logs in with your Telegram user account (same
TELEGRAM_API_ID/API_HASH as the bot) and lists every chat you're in, so you
can copy the right ID.

Usage:
    python list_chats.py [filter text]

    python list_chats.py                 # lists everything
    python list_chats.py "premium"       # only chats whose name contains "premium"

The first run asks for your phone number and login code, same as main.py -
it reuses the same session file (TELEGRAM_SESSION_NAME), so you only need
to log in once across both scripts.
"""
from __future__ import annotations

import asyncio
import sys

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from config import load_config


async def main() -> None:
    config = load_config()
    name_filter = sys.argv[1].lower() if len(sys.argv) > 1 else None

    client = TelegramClient(config.telegram_session_name, config.telegram_api_id, config.telegram_api_hash)

    async with client:
        print(f"{'ID':>16}  {'Type':<9} Name")
        print("-" * 70)
        async for dialog in client.iter_dialogs():
            if name_filter and name_filter not in dialog.name.lower():
                continue

            entity = dialog.entity
            if isinstance(entity, Channel):
                kind = "group" if entity.megagroup else "channel"
            elif isinstance(entity, Chat):
                kind = "group"
            elif isinstance(entity, User):
                kind = "user"
            else:
                kind = "?"

            print(f"{dialog.id:>16}  {kind:<9} {dialog.name}")

    print("\nSkopiuj interesujące Cie ID (razem ze znakiem '-', jesli jest) do TELEGRAM_CHANNEL w .env")


if __name__ == "__main__":
    asyncio.run(main())
