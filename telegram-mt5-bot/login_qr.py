"""Alternative login for when typing the SMS/in-app code keeps failing
(e.g. terminal paste issues, or the code never arrives): scan a QR code
with Telegram on your phone instead.

Saves to the same session file as the rest of the bot (TELEGRAM_SESSION_NAME
in .env), so once you're logged in here, list_chats.py and main.py just
work without asking again.

Usage:
    python login_qr.py
"""
from __future__ import annotations

import asyncio

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import load_config


async def main() -> None:
    config = load_config()
    client = TelegramClient(config.telegram_session_name, config.telegram_api_id, config.telegram_api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Juz zalogowany jako {me.first_name} ({me.phone}). Nic wiecej nie trzeba robic.")
        await client.disconnect()
        return

    qr_login = await client.qr_login()

    while True:
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_login.url)
        qr.make()
        print("\nNa telefonie otworz Telegram -> Ustawienia -> Urzadzenia")
        print("-> \"Polacz biurkowe urzadzenie\" (Link Desktop Device) -> zeskanuj ten kod:\n")
        qr.print_ascii(invert=True)
        print("\n(kod wazny okolo minuty - jesli wygasnie, pokaze sie nowy automatycznie)")

        try:
            await qr_login.wait(60)
            break
        except asyncio.TimeoutError:
            print("Kod wygasl, generuje nowy...")
            await qr_login.recreate()
            continue
        except SessionPasswordNeededError:
            password = input("\nMasz wlaczona weryfikacje dwuetapowa - podaj haslo Telegrama: ")
            await client.sign_in(password=password)
            break

    me = await client.get_me()
    print(f"\nZalogowano jako {me.first_name} ({me.phone}).")
    print("Mozesz teraz uruchomic: python list_chats.py")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
