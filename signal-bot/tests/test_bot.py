import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reports  # noqa: E402
from signal_parser import StrategyMatcher, diff_updates, parse_signal, parse_update  # noqa: E402
from storage import Storage  # noqa: E402

SM = StrategyMatcher()
TZ = ZoneInfo("Europe/Warsaw")

GOLD = """🔥 Strategia nr 1
XAUUSD BUY 2350
SL: 2340
TP1: 2353
TP2: 2356
TP3: 2365"""

EURUSD = """Strategy #3
EUR/USD SELL @ 1.0850
TP1 1.0830
TP2 1.0810
SL 1.0880"""

PIPS_SIG = """#S2 GBPJPY buy now 191.20
TP1: 30 pips
TP2: 60 pips
SL: 40 pips"""


def test_parse_gold():
    s = parse_signal(GOLD, SM)
    assert s.symbol == "XAUUSD" and s.direction == "BUY" and s.strategy == "1"
    assert s.entry == 2350 and s.sl == 2340
    assert [v for v, _ in s.tps] == [2353, 2356, 2365]


def test_parse_eurusd():
    s = parse_signal(EURUSD, SM)
    assert s.symbol == "EURUSD" and s.direction == "SELL" and s.strategy == "3"
    assert s.entry == 1.0850 and [v for v, _ in s.tps] == [1.0830, 1.0810]


def test_parse_pips_signal():
    s = parse_signal(PIPS_SIG, SM)
    assert s.strategy == "2" and s.symbol == "GBPJPY"
    assert s.tps == [(30, True), (60, True)] and s.sl_is_pips


def test_not_a_signal():
    assert parse_signal("TP2 hit ✅ +60 pips", SM) is None
    assert parse_signal("Dzień dobry, dziś spokojny rynek", SM) is None


def test_parse_updates():
    u = parse_update("TP2 ✅ +60 pips")
    assert u.tp_hits == {2} and u.pips == 60
    assert parse_update("✅ TP3 zaliczone").tp_hits == {3}
    assert parse_update("XAUUSD all TP hit 🔥").all_tps
    assert parse_update("SL hit ❌").sl_hit
    assert not parse_update("Przesuńcie SL na BE").sl_hit
    assert parse_update("Dzień dobry").empty


def test_edit_diff():
    edited = GOLD.replace("TP2: 2356", "TP2: 2356 ✅").replace("TP1: 2353", "TP1: 2353 ✅")
    u = diff_updates(parse_update(GOLD), parse_update(edited))
    assert u.tp_hits == {1, 2}


def _store(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    when = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)
    st.add_signal(-100, 1, when, parse_signal(GOLD, SM), GOLD)
    st.add_signal(-100, 2, when, parse_signal(EURUSD, SM), EURUSD)
    st.add_signal(-100, 3, when, parse_signal(PIPS_SIG, SM), PIPS_SIG)
    return st


def test_highest_tp_only(tmp_path):
    st = _store(tmp_path)
    for text in ["TP1 ✅", "TP3 ✅", "TP2 ✅"]:  # kolejność nie ma znaczenia
        st.apply_update(st.get(-100, 1), parse_update(text))
    s = st.get(-100, 1)
    assert s.max_tp == 3 and s.pips == 150  # (2365-2350)/0.1, nie suma TP1+TP2+TP3

    st.apply_update(st.get(-100, 2), parse_update("TP2 hit"))
    assert st.get(-100, 2).pips == 40

    st.apply_update(st.get(-100, 3), parse_update("SL hit"))
    assert st.get(-100, 3).sl_hit and st.get(-100, 3).loss_pips == 40


def test_sl_after_tp_is_not_loss(tmp_path):
    st = _store(tmp_path)
    st.apply_update(st.get(-100, 1), parse_update("TP1 ✅"))
    st.apply_update(st.get(-100, 1), parse_update("SL hit"))
    s = st.get(-100, 1)
    assert s.max_tp == 1 and not s.sl_hit and s.pips == 30


def test_report(tmp_path):
    st = _store(tmp_path)
    st.apply_update(st.get(-100, 1), parse_update("TP3 ✅"))
    st.apply_update(st.get(-100, 2), parse_update("TP2 ✅"))
    st.apply_update(st.get(-100, 3), parse_update("SL hit"))
    start, end = reports.day_range(date(2026, 11, 11), TZ)
    rows = st.between(-100, start, end)
    names = {s: f"Strategia nr {s}" for s in "123"}
    txt = reports.build_report("Test", rows, ["1", "2", "3"], names, False, True, TZ)
    assert "Strategia nr 1</b>: <b>+150 pips" in txt
    assert "Strategia nr 2</b>: <b>+0 pips" in txt
    assert "Strategia nr 3</b>: <b>+40 pips" in txt
    assert "Razem: +190 pips" in txt
    txt2 = reports.build_report("Test", rows, ["1", "2", "3"], names, True, False, TZ)
    assert "Razem: +150 pips" in txt2


def test_ranges():
    s, e = reports.week_range(date(2026, 11, 11), TZ)
    assert s.date() == date(2026, 11, 9) and e.date() == date(2026, 11, 16)
    s, e = reports.month_range(date(2026, 12, 5), TZ)
    assert s.date() == date(2026, 12, 1) and e.date() == date(2027, 1, 1)
    assert reports.is_last_day_of_month(date(2026, 11, 30))
