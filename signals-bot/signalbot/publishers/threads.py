from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

API = "https://graph.threads.net/v1.0"
REFRESH_EVERY = 3 * 24 * 3600   # token long-lived (60 dni) odświeżamy co 3 dni

log = logging.getLogger(__name__)


def upload_image(image: Path, imgbb_key: str = "") -> str:
    """Wgrywa wykres na publiczny hosting (Threads pobiera obrazek z URL).
    Z IMGBB_API_KEY -> imgbb.com, bez klucza -> catbox.moe."""
    with open(image, "rb") as f:
        if imgbb_key:
            r = requests.post("https://api.imgbb.com/1/upload", data={"key": imgbb_key},
                              files={"image": f}, timeout=60)
            return r.json()["data"]["url"]
        r = requests.post("https://catbox.moe/user/api.php", data={"reqtype": "fileupload"},
                          files={"fileToUpload": f}, timeout=60)
    url = r.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"upload obrazka nieudany: {url[:200]}")
    return url


class ThreadsPublisher:
    """Threads API (Meta). Obrazek: PUBLIC_IMAGE_BASE_URL + ścieżka w data/, a gdy go brak -
    automatyczny upload (imgbb / catbox). Token sam się odświeża i jest trzymany w data/threads_token.json."""

    def __init__(self, user_id: str, token: str, public_base: str, data_dir: Path, imgbb_key: str = ""):
        self.public_base, self.data_dir = public_base, Path(data_dir)
        self.imgbb_key = imgbb_key
        self.token_file = self.data_dir / "threads_token.json"
        self.env_token = token
        self.token, self.refreshed = token, 0.0
        try:
            saved = json.loads(self.token_file.read_text(encoding="utf-8"))
            if saved.get("env_token_tail") == token[-12:]:   # nowy token w .env wygrywa z zapisanym
                self.token, self.refreshed = saved["token"], saved.get("refreshed", 0.0)
        except (OSError, ValueError, KeyError):
            pass
        self.user_id = user_id or self._get("me", fields="id")["id"]

    def _check(self, r: requests.Response) -> dict:
        js = r.json()
        if "error" in js:
            raise RuntimeError(f"Threads: {js['error'].get('message', js)}")
        return js

    def _get(self, path: str, **params) -> dict:
        return self._check(requests.get(f"{API}/{path}", params={**params, "access_token": self.token}, timeout=30))

    def _post(self, path: str, **params) -> dict:
        return self._check(requests.post(f"{API}/{path}", params={**params, "access_token": self.token}, timeout=60))

    def _refresh(self) -> None:
        if time.time() - self.refreshed < REFRESH_EVERY:
            return
        try:
            js = self._check(requests.get("https://graph.threads.net/refresh_access_token",
                                           params={"grant_type": "th_refresh_token", "access_token": self.token},
                                           timeout=30))
            self.token, self.refreshed = js["access_token"], time.time()
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(json.dumps({"token": self.token, "refreshed": self.refreshed,
                                                   "env_token_tail": self.env_token[-12:]}), encoding="utf-8")
            log.info("Threads: token odświeżony (ważny %d dni)", js.get("expires_in", 0) // 86400)
        except Exception as e:  # np. token młodszy niż 24 h - spróbujemy przy następnym poście
            log.warning("Threads: odświeżenie tokenu nieudane: %s", e)

    def _image_url(self, image: Path) -> str:
        if self.public_base:
            rel = Path(image).resolve().relative_to(self.data_dir.resolve()).as_posix()
            return f"{self.public_base}/{rel}"
        return upload_image(image, self.imgbb_key)

    def _wait_ready(self, container: str) -> None:
        for _ in range(20):
            time.sleep(3)
            status = self._get(container, fields="status,error_message")
            if status.get("status") == "FINISHED":
                return
            if status.get("status") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Threads: kontener {status.get('status')}: {status.get('error_message')}")
        raise RuntimeError("Threads: kontener nie przetworzył się w 60 s")

    def publish(self, text: str, image: Path | None = None, reply_to: str | None = None) -> str:
        self._refresh()
        params = {"text": text[:500], "media_type": "TEXT"}
        if reply_to:
            params["reply_to_id"] = reply_to
        if image:
            try:
                params.update(media_type="IMAGE", image_url=self._image_url(image))
            except Exception as e:
                log.warning("Threads: brak obrazka (%s) - wysyłam sam tekst", e)
        container = self._post(f"{self.user_id}/threads", **params)["id"]
        self._wait_ready(container)
        return self._post(f"{self.user_id}/threads_publish", creation_id=container)["id"]

    def me(self) -> dict:
        return self._get("me", fields="id,username")
