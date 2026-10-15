import numpy as np
import pandas as pd
import pytest

from signalbot.data import SyntheticProvider
from signalbot.strategy import find_setups
from signalbot.tracker import evaluate


def bars_from_path(points, base=1000.0):
    """Ścieżka zamknięć z odcinków liniowych: [(cena, liczba_świec), ...]."""
    closes = [points[0][0]]
    for price, n in points[1:]:
        closes += list(np.linspace(closes[-1], price, n + 1)[1:])
    closes = np.array(closes) + base
    opens = np.r_[closes[0], closes[:-1]]
    df = pd.DataFrame(dict(
        time=pd.date_range("2026-01-05", periods=len(closes), freq="30min", tz="UTC"),
        open=opens, close=closes,
        high=np.maximum(opens, closes) + 0.2, low=np.minimum(opens, closes) - 0.2,
    ))
    return df


# warmup -> HL 105 -> HH 112 -> BOS do 95 -> retest 107 -> spadek
SELL_PATH = [(100, 0), (101, 10), (100, 10), (110, 10), (105, 5), (112, 7), (95, 6),
             (107, 6), (98, 6), (96, 4)]


def test_detects_sell_setup_with_structural_sl_tp():
    df = bars_from_path(SELL_PATH)
    setups = [s for s in find_setups(df) if s.direction == "SELL"]
    assert len(setups) == 1
    s = setups[0]
    assert s.break_type == "CHOCH"  # przed przebiciem: wyższe szczyty i dołki
    assert s.level == pytest.approx(1104.8)
    assert s.tp == pytest.approx(df["low"].iloc[s.extreme_idx])
    assert s.tp == pytest.approx(1094.8)
    retest_high = df["high"].iloc[s.retest_idx]
    assert retest_high >= s.level and s.sl > retest_high
    assert s.tp < s.entry < s.level < s.sl
    assert s.rr == pytest.approx((s.entry - s.tp) / (s.sl - s.entry))


def test_buy_is_mirror_of_sell():
    df = bars_from_path(SELL_PATH, base=0)
    m = df.copy()
    m["open"], m["close"] = 3000 - df["open"], 3000 - df["close"]
    m["high"], m["low"] = 3000 - df["low"], 3000 - df["high"]
    sell = [s for s in find_setups(df) if s.direction == "SELL"][0]
    buy = [s for s in find_setups(m) if s.direction == "BUY"][0]
    assert buy.confirm_idx == sell.confirm_idx
    assert buy.entry == pytest.approx(3000 - sell.entry)
    assert buy.sl == pytest.approx(3000 - sell.sl)
    assert buy.tp == pytest.approx(3000 - sell.tp)


def test_no_lookahead():
    """Setup wykryty na pełnej historii musi być widoczny już w chwili potwierdzenia."""
    df = SyntheticProvider(seed=3).get_bars("x", "M30", 2500)
    full = find_setups(df)
    assert full
    for s in full:
        live = find_setups(df.iloc[: s.confirm_idx + 1])
        match = [x for x in live if x.confirm_idx == s.confirm_idx and x.direction == s.direction]
        assert match and match[0].entry == s.entry and match[0].sl == s.sl and match[0].tp == s.tp


def _bars(rows):
    return pd.DataFrame(
        [dict(time=pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=30 * i),
              open=o, high=h, low=l, close=c) for i, (o, h, l, c) in enumerate(rows)]
    )


def test_evaluate_tp_sl_and_same_bar():
    tp = evaluate(_bars([(100, 101, 97, 98), (98, 99, 89, 90)]), "SELL", 100, 105, 90)
    assert tp.outcome == "tp" and tp.r == pytest.approx(2.0)
    sl = evaluate(_bars([(100, 106, 99, 104)]), "SELL", 100, 105, 90)
    assert sl.outcome == "sl" and sl.r == -1
    both = evaluate(_bars([(100, 106, 89, 95)]), "SELL", 100, 105, 90)
    assert both.outcome == "sl"
    assert evaluate(_bars([(100, 101, 99, 100)]), "BUY", 100, 95, 110) is None
