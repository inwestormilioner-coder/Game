"""File-based relay for zone signals between two bot instances that can't
each have their own live Telegram connection.

Why this exists: running a second MT5 account needs a second Python
process (the MetaTrader5 package only supports one connected terminal per
process), and a second process listening on Telegram needs its own
Telethon session. But two Telethon sessions built from copies of the SAME
login can't both reliably receive live updates at once - in practice only
one of the two ends up getting push notifications for new channel/manual-
chat messages, and it can flip between them unpredictably. Getting a
GENUINE second login working (its own phone/code verification) is the
correct fix when possible - this relay is the fallback for when that
isn't (e.g. the account isn't receiving login codes).

One instance (SIGNAL_RELAY_ROLE=source in config.py - the one with the
actually-working Telegram session) writes every raw message it receives on
the channel/manual chat to a shared folder, via write_relay_signal, in
ADDITION to handling it normally itself. The other instance
(SIGNAL_RELAY_ROLE=consumer) doesn't subscribe to Telegram updates at all -
watch_relay_folder polls that same folder and feeds each file it finds
through the consumer's own handle_text(), exactly as if it had received it
directly from Telegram.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("signal_relay")

MessageHandler = Callable[[str], Awaitable[None]]

# Strictly-increasing per-process counter appended to each relay filename -
# a millisecond timestamp alone isn't unique/ordered enough: two messages
# landing in the same millisecond would either collide (one silently
# clobbers the other's file) or, with a random suffix instead, sort out of
# order. Windows' clock resolution (often ~15ms by default) makes this a
# real risk, not just a theoretical one. The counter guarantees both
# uniqueness and correct chronological ordering regardless of clock
# granularity, as long as write_relay_signal is only ever called from one
# process (the "source" instance) - which is the only supported setup.
_sequence = itertools.count()


def write_relay_signal(folder: Path, text: str) -> Path:
    """Writes one relayed message as a plain text file, via a temp file +
    atomic rename so watch_relay_folder never reads a file mid-write - same
    reasoning as mt5_executor._write_command's bridge command files."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"signal_{int(time.time() * 1000)}_{next(_sequence):06d}.txt"
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
    return path


async def watch_relay_folder(folder: Path, on_message: MessageHandler, poll_seconds: float = 2.0) -> None:
    """Runs forever, polling `folder` for files written by write_relay_signal
    (oldest first, by filename - the timestamp in the name sorts
    chronologically) and feeding each one's text through on_message, same
    as a live Telegram message would go through Bot.handle_text. Each file
    is deleted right after being read, before calling on_message, so a
    handler error doesn't leave it to be endlessly retried."""
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        for path in sorted(folder.glob("*.txt")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue  # still being written - pick it up next poll
            path.unlink(missing_ok=True)
            log.info("relayed signal from %s: %s", path.name, text.replace("\n", " | "))
            try:
                await on_message(text)
            except Exception:
                log.exception("error handling relayed signal from %s", path.name)
        await asyncio.sleep(poll_seconds)
