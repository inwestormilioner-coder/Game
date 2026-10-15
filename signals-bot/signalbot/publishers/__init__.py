"""Publikacja na Telegram, Threads i X. Każdy publisher zwraca id posta (do odpowiedzi z wynikiem)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class DryRunPublisher:
    """Nic nie wysyła — wypisuje, co zostałoby opublikowane."""

    def __init__(self, name: str):
        self.name = name

    def publish(self, text: str, image: Path | None = None, reply_to: str | None = None) -> str:
        log.info("[DRY RUN %s] reply_to=%s image=%s\n%s", self.name, reply_to, image, text)
        return f"dry-{self.name}"


def make_publishers(cfg) -> dict:
    """{nazwa: (publisher, rodzaj_tekstu)} — rodzaj to 'long' albo 'short'."""
    from .telegram import TelegramPublisher
    from .threads import ThreadsPublisher
    from .x import XPublisher

    pubs = {}
    if cfg.telegram_enabled:
        pubs["telegram"] = (TelegramPublisher(cfg.telegram_bot_token, cfg.telegram_chat_id), "long")
    if cfg.threads_enabled:
        pubs["threads"] = (ThreadsPublisher(cfg.threads_user_id, cfg.threads_access_token,
                                            cfg.public_image_base_url, cfg.data_dir), "threads")
    if cfg.x_enabled:
        pubs["x"] = (XPublisher(cfg.x_api_key, cfg.x_api_secret, cfg.x_access_token,
                                cfg.x_access_secret), "short")
    if cfg.dry_run:
        pubs = {name: (DryRunPublisher(name), kind) for name, (_, kind) in pubs.items()} or {
            "console": (DryRunPublisher("console"), "long")
        }
    return pubs
