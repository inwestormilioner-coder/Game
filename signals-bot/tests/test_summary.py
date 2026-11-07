import pandas as pd

from signalbot.summary import book_exit

T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def test_be_after_tp_keeps_pips():
    a = {"direction": "SELL", "levels": {"entry": 4030.0}}
    book_exit(a, "tp1", 45, T("2026-10-26 10:00"))
    book_exit(a, "tp2", 80, T("2026-10-26 12:00"))
    book_exit(a, "sl", 0, T("2026-10-26 14:00"))          # BE po TP - bez zmiany
    b = {"direction": "BUY", "levels": {"entry": 4000.0}}
    book_exit(b, "sl", -50, T("2026-10-26 16:00"))
    assert a["pips"] == 80 and b["pips"] == -50


def test_ai_exit_counts_furthest():
    a = {"direction": "SELL", "levels": {"entry": 4290.0}}
    book_exit(a, "tp3", 260, T("2026-10-26 10:00"))
    book_exit(a, "rev", 86, T("2026-10-26 12:00"))        # AI bliżej niż TP3 -> zostaje 260
    b = {"direction": "BUY", "levels": {"entry": 4000.0}}
    book_exit(b, "tp1", 40, T("2026-10-26 10:00"))
    book_exit(b, "rev", 95, T("2026-10-26 12:00"))        # AI dalej niż TP1 -> 95
    assert a["pips"] == 260 and b["pips"] == 95
