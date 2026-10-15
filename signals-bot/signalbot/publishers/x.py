from __future__ import annotations

from pathlib import Path

import requests
from requests_oauthlib import OAuth1

API = "https://api.x.com/2"


class XPublisher:
    """X API v2, OAuth 1.0a (klucze aplikacji + access token konta z uprawnieniem Read and Write).
    Publikowanie przez API jest płatne — sprawdź aktualny plan na developer.x.com."""

    def __init__(self, api_key: str, api_secret: str, token: str, token_secret: str):
        self.auth = OAuth1(api_key, api_secret, token, token_secret)

    def _upload(self, image: Path) -> str:
        with open(image, "rb") as f:
            r = requests.post(f"{API}/media/upload", auth=self.auth, timeout=60,
                              files={"media": f}, data={"media_category": "tweet_image"})
        r.raise_for_status()
        return r.json()["data"]["id"]

    def publish(self, text: str, image: Path | None = None, reply_to: str | None = None) -> str:
        body: dict = {"text": text[:280]}
        if image:
            body["media"] = {"media_ids": [self._upload(image)]}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        r = requests.post(f"{API}/tweets", auth=self.auth, json=body, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"X: {r.status_code} {r.text}")
        return r.json()["data"]["id"]
