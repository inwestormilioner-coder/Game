import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signal_relay import watch_relay_folder, write_relay_signal  # noqa: E402


def test_write_relay_signal_creates_a_readable_text_file(tmp_path):
    path = write_relay_signal(tmp_path, "Kierunek: Buy Gold\nStrefa: 4397-4402\nSL: 60 pips")

    assert path.exists()
    assert path.suffix == ".txt"
    assert path.read_text(encoding="utf-8") == "Kierunek: Buy Gold\nStrefa: 4397-4402\nSL: 60 pips"


def test_write_relay_signal_creates_the_folder_if_missing(tmp_path):
    folder = tmp_path / "relay"
    assert not folder.exists()

    write_relay_signal(folder, "hello")

    assert folder.exists()


async def _run_one_poll(folder, on_message):
    task = asyncio.ensure_future(watch_relay_folder(folder, on_message, poll_seconds=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_watch_relay_folder_delivers_a_written_signal_and_deletes_it(tmp_path):
    write_relay_signal(tmp_path, "Kierunek: Sell Gold\nStrefa: 4400-4405\nSL: 60 pips")

    received = []

    async def on_message(text):
        received.append(text)

    asyncio.run(_run_one_poll(tmp_path, on_message))

    assert received == ["Kierunek: Sell Gold\nStrefa: 4400-4405\nSL: 60 pips"]
    assert list(tmp_path.glob("*.txt")) == []


def test_watch_relay_folder_delivers_multiple_signals_in_order(tmp_path):
    write_relay_signal(tmp_path, "first")
    write_relay_signal(tmp_path, "second")

    received = []

    async def on_message(text):
        received.append(text)

    asyncio.run(_run_one_poll(tmp_path, on_message))

    assert received == ["first", "second"]


def test_watch_relay_folder_keeps_polling_after_a_handler_error(tmp_path):
    write_relay_signal(tmp_path, "bad")
    write_relay_signal(tmp_path, "good")

    received = []

    async def on_message(text):
        if text == "bad":
            raise RuntimeError("boom")
        received.append(text)

    asyncio.run(_run_one_poll(tmp_path, on_message))

    assert received == ["good"]
    assert list(tmp_path.glob("*.txt")) == []
