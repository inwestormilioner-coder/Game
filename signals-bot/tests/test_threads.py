from pathlib import Path
from unittest import mock

from signalbot.publishers import threads as th


class R:
    def __init__(self, js=None, text=""):
        self._js, self.text = js, text

    def json(self):
        return self._js


def test_publish_uploads_image_and_waits(tmp_path: Path):
    img = tmp_path / "c.png"
    img.write_bytes(b"png")
    calls = []

    def post(url, params=None, data=None, files=None, timeout=None):
        calls.append((url, params))
        if "catbox" in url:
            return R(text="https://files.catbox.moe/abc.png")
        if url.endswith("/threads"):
            return R({"id": "C1"})
        return R({"id": "P1"})

    def get(url, params=None, timeout=None):
        if "refresh_access_token" in url:
            return R({"access_token": "NEW", "expires_in": 5184000})
        return R({"status": "FINISHED"})

    with mock.patch.object(th.requests, "post", post), mock.patch.object(th.requests, "get", get), \
            mock.patch.object(th.time, "sleep"):
        pub = th.ThreadsPublisher("42", "OLDTOKEN", "", tmp_path)
        assert pub.publish("hello", img) == "P1"
        assert pub.publish("why", reply_to="P1") == "P1"
    create = [p for u, p in calls if u.endswith("/threads")]
    assert create[0]["image_url"] == "https://files.catbox.moe/abc.png" and create[0]["media_type"] == "IMAGE"
    assert create[1]["reply_to_id"] == "P1" and create[1]["media_type"] == "TEXT"
    assert create[0]["access_token"] == "NEW"
    # zapisany token jest używany przy kolejnym starcie z tym samym tokenem w .env
    with mock.patch.object(th.requests, "get", get):
        assert th.ThreadsPublisher("42", "OLDTOKEN", "", tmp_path).token == "NEW"
        assert th.ThreadsPublisher("42", "FRESHTOKEN", "", tmp_path).token == "FRESHTOKEN"
