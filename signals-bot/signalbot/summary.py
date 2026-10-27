"""Podsumowania dzienne i tygodniowe w pipsach.

Wynik sygnału = pipsy do najwyższego trafionego TP (zamknięcie na BE po TP niczego nie odejmuje),
a gdy żadnego TP nie było - pipsy z SL / zamknięcia. Każda zmiana wyniku trafia do rec["pip_log"]
jako [czas UTC, przyrost], więc sygnał rozliczony w dwa dni liczy się do obu dni po kawałku.
"""
from __future__ import annotations

import pandas as pd

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def book_exit(rec: dict, name: str, pips: float, when: pd.Timestamp) -> None:
    """Zapisz wynik po wyjściu (TPk / sl / timeout) do dziennika pipsów sygnału."""
    best = rec.get("pips")
    if name.startswith("tp"):
        new = pips if best is None else max(best, pips)
    elif rec.get("tp_hit"):
        return                      # po TP: BE / zamknięcie nie zmienia wyniku
    else:
        new = pips
    if name.startswith("tp"):
        rec["tp_hit"] = int(name[2:])
    elif name == "sl":
        rec["sl_hit"] = True
    delta = new - (best or 0.0)
    rec["pips"] = new
    if abs(delta) >= 0.05:
        rec.setdefault("pip_log", []).append([pd.Timestamp(when).isoformat(), round(delta, 1)])


def _rows(signals: dict, start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[dict, float]]:
    out = []
    for rec in signals.values():
        d = sum(p for t, p in rec.get("pip_log", []) if start < pd.Timestamp(t) <= end)
        if any(start < pd.Timestamp(t) <= end for t, _ in rec.get("pip_log", [])):
            out.append((rec, d))
    return out


def summary_text(signals: dict, start: pd.Timestamp, end: pd.Timestamp, symbol: str, weekly: bool) -> str | None:
    rows = _rows(signals, start, end)
    if not rows:
        return None
    total = sum(d for _, d in rows)
    wins = sum(1 for rec, _ in rows if rec.get("tp_hit"))
    losses = sum(1 for rec, _ in rows if not rec.get("tp_hit") and rec.get("pips", 0) < 0)
    if weekly:
        head = f"📅 {symbol} weekly recap · {start + pd.Timedelta(days=1):%d %b} – {end:%d %b}"
    else:
        head = f"📊 {symbol} daily recap · {DAYS[end.weekday()]} {end:%d %b}"
    lines = [head, ""]
    if not weekly:
        for rec, d in rows:
            lv = rec.get("levels", {})
            res = f"TP{rec['tp_hit']}" if rec.get("tp_hit") else ("SL" if rec.get("sl_hit") else "closed")
            lines.append(f"{'🟢' if rec['direction'] == 'BUY' else '🔴'} {rec['direction']} "
                         f"{lv.get('entry', 0):.2f} → {res} {d:+.0f} pips")
        lines.append("")
    lines.append(f"✅ Winners: {wins}   ❌ Losers: {losses}")
    lines.append(f"{'💰' if total >= 0 else '📉'} Total: {total:+.0f} pips")
    return "\n".join(lines)


def due_summaries(meta: dict, now: pd.Timestamp, hour_utc: int) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """Które podsumowania wysłać teraz: [(rodzaj, od, do)]. Dzienne pn–pt po `hour_utc`, tygodniowe w piątek."""
    out = []
    if now.weekday() >= 5 or now.hour < hour_utc:
        return out
    cut = now.normalize() + pd.Timedelta(hours=hour_utc)
    last_d = pd.Timestamp(meta["daily_at"]) if meta.get("daily_at") else cut - pd.Timedelta(days=1)
    if last_d < cut:
        # poniedziałek obejmuje też weekendowe domknięcia od piątkowego podsumowania
        out.append(("daily", last_d, cut))
    if now.weekday() == 4:
        last_w = pd.Timestamp(meta["weekly_at"]) if meta.get("weekly_at") else cut - pd.Timedelta(days=7)
        if last_w < cut:
            out.append(("weekly", last_w, cut))
    return out
