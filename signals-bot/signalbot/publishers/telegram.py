from __future__ import annotations

from pathlib import Path

import requests


class TelegramPublisher:
    """Bot musi być administratorem grupy/kanału. chat_id grupy zaczyna się od -100…"""

    def __init__(self, token: str, chat_id: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    def publish(self, text: str, image: Path | None = None, reply_to: str | None = None) -> str:
        data = {"chat_id": self.chat_id}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        if image:
            with open(image, "rb") as f:
                r = requests.post(f"{self.base}/sendPhoto", data={**data, "caption": text[:1024]},
                                  files={"photo": f}, timeout=60)
        else:
            r = requests.post(f"{self.base}/sendMessage", data={**data, "text": text}, timeout=30)
        js = r.json()
        if not js.get("ok"):
            raise RuntimeError(f"Telegram: {js.get('description', js)}")
        return str(js["result"]["message_id"])
