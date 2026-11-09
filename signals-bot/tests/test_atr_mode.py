import pytest

from signalbot.config import load_config
from signalbot.data import SyntheticProvider
from signalbot.fib_live import fib_params
from signalbot.fibzone import _atr, find_fib_trades
from signalbot.writer_fib import levels


def test_atr_mode_levels_are_r_multiples_of_atr_stop():
    cfg = load_config(None)
    cfg.risk_mode, cfg.sl_atr, cfg.tp_r, cfg.ai_manager = "atr", 2.0, (1.0, 2.0, 3.0, 4.0, 5.0), False
    df = SyntheticProvider(seed=2).get_bars("XAU/USD", "M15", 3000)
    trades = find_fib_trades(df, fib_params(cfg))
    assert trades
    a = _atr(*(df[k].to_numpy(dtype=float) for k in ("high", "low", "close")))
    for tr in trades:
        lv = levels(tr)                                  # to samo, co trafia do posta i na MT5
        risk = abs(lv["entry"] - tr.sl)
        assert risk == pytest.approx(2.0 * a[tr.entry_idx - 1], rel=1e-6)
        s = 1 if tr.direction == "BUY" else -1
        assert lv["tps"] == pytest.approx([lv["entry"] + s * r * risk for r in cfg.tp_r], abs=0.05)


def test_fib_mode_unchanged():
    cfg = load_config(None)
    cfg.risk_mode, cfg.ai_manager = "fib", False
    p = fib_params(cfg)
    assert p.tps == (0.382, 0.618, 1.0, 1.272, 1.618)
    for tr in find_fib_trades(SyntheticProvider(seed=2).get_bars("XAU/USD", "M15", 3000), p):
        assert tr.sl == pytest.approx(tr.fib0 - 0.1272 * (tr.fib1 - tr.fib0))
