import pandas as pd

from signalbot.summary import book_exit, due_summaries, summary_text

T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def test_be_after_tp_keeps_pips_and_recap():
    a = {"direction": "SELL", "levels": {"entry": 4030.0}}
    book_exit(a, "tp1", 45, T("2026-10-26 10:00"))
    book_exit(a, "tp2", 80, T("2026-10-26 12:00"))
    book_exit(a, "sl", 0, T("2026-10-26 14:00"))          # BE po TP - bez zmiany
    b = {"direction": "BUY", "levels": {"entry": 4000.0}}
    book_exit(b, "sl", -50, T("2026-10-26 16:00"))
    assert a["pips"] == 80 and b["pips"] == -50
    text = summary_text({"a": a, "b": b}, T("2026-10-25 21:00"), T("2026-10-26 21:00"), "XAUUSD", False)
    assert "SELL 4030.00 → TP2 +80 pips" in text and "BUY 4000.00 → SL -50 pips" in text
    assert "Winners: 1" in text and "Losers: 1" in text and "Total: +30 pips" in text


def test_due():
    fri = T("2026-10-30 21:15")
    assert [k for k, *_ in due_summaries({}, fri, 21)] == ["daily", "weekly"]
    assert due_summaries({}, T("2026-10-30 20:45"), 21) == []
    assert due_summaries({}, T("2026-10-31 21:15"), 21) == []           # sobota
    meta = {"daily_at": T("2026-10-30 21:00").isoformat(), "weekly_at": T("2026-10-30 21:00").isoformat()}
    assert due_summaries(meta, fri, 21) == []


def test_ai_exit_counts_furthest():
    a = {"direction": "SELL", "levels": {"entry": 4290.0}}
    book_exit(a, "tp3", 260, T("2026-10-26 10:00"))
    book_exit(a, "rev", 86, T("2026-10-26 12:00"))        # AI bliżej niż TP3 -> zostaje 260
    b = {"direction": "BUY", "levels": {"entry": 4000.0}}
    book_exit(b, "tp1", 40, T("2026-10-26 10:00"))
    book_exit(b, "rev", 95, T("2026-10-26 12:00"))        # AI dalej niż TP1 -> 95
    assert a["pips"] == 260 and b["pips"] == 95
    text = summary_text({"a": a, "b": b}, T("2026-10-25 21:00"), T("2026-10-26 21:00"), "XAUUSD", False)
    assert "BUY 4000.00 → AI exit +95 pips" in text and "Total: +355 pips" in text
