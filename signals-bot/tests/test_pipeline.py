from signalbot.config import Config
from signalbot.data import SyntheticProvider
from signalbot.main import run_once
from signalbot.strategy import find_setups
from signalbot.tracker import State


class FakePublisher:
    def __init__(self):
        self.calls = []

    def publish(self, text, image=None, reply_to=None):
        self.calls.append((text, image, reply_to))
        return f"msg{len(self.calls)}"


class SliceProvider:
    def __init__(self, df):
        self.df = df

    def get_bars(self, symbol, timeframe, count=None):
        return self.df


def test_publishes_once_then_reports_result(tmp_path):
    full = SyntheticProvider(seed=1).get_bars("x", "M30", 3000)
    s = find_setups(full)[0]
    cfg = Config(data_source="synthetic", use_ai=False, data_dir=tmp_path)
    state = State(tmp_path / "state.json")
    pub = FakePublisher()
    pubs = {"telegram": (pub, "long")}

    live = SliceProvider(full.iloc[: s.confirm_idx + 1].reset_index(drop=True))
    run_once(cfg, live, state, pubs)
    run_once(cfg, live, state, pubs)  # ten sam stan rynku -> bez duplikatu
    assert len(pub.calls) == 1
    text, image, _ = pub.calls[0]
    assert "SETUP" in text and f"{s.entry:.2f}" in text and image.exists()

    run_once(cfg, SliceProvider(full), state, pubs)
    rec = next(iter(State(tmp_path / "state.json").signals.values()))
    assert rec["status"] == "closed" and rec["outcome"] in ("tp", "sl", "timeout")
    assert pub.calls[1][2] == "msg1"  # wynik jako odpowiedź na post z sygnałem
