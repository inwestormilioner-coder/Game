from __future__ import annotations

import time
from pathlib import Path

import requests

API = "https://graph.threads.net/v1.0"


class ThreadsPublisher:
    """Threads API (Meta). Obrazek musi być dostępny pod publicznym URL:
    PUBLIC_IMAGE_BASE_URL + /charts/<plik>.png (np. katalog data/ wystawiony przez nginx).
    Bez tego URL post idzie jako sam tekst."""

    def __init__(self, user_id: str, token: str, public_base: str, data_dir: Path):
        self.user_id, self.token = user_id, token
        self.public_base, self.data_dir = public_base, Path(data_dir)

    def _post(self, path: str, **params) -> dict:
        r = requests.post(f"{API}/{path}", params={**params, "access_token": self.token}, timeout=60)
        js = r.json()
        if "error" in js:
            raise RuntimeError(f"Threads: {js['error'].get('message', js)}")
        return js

    def publish(self, text: str, image: Path | None = None, reply_to: str | None = None) -> str:
        params = {"text": text[:500]}
        if reply_to:
            params["reply_to_id"] = reply_to
        if image and self.public_base:
            rel = Path(image).resolve().relative_to(self.data_dir.resolve()).as_posix()
            params.update(media_type="IMAGE", image_url=f"{self.public_base}/{rel}")
        else:
            params["media_type"] = "TEXT"
        container = self._post(f"{self.user_id}/threads", **params)["id"]
        time.sleep(10)  # Meta zaleca chwilę odczekać, aż kontener się przetworzy
        return self._post(f"{self.user_id}/threads_publish", creation_id=container)["id"]
