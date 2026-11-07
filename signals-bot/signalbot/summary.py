"""Wynik sygnału w pipsach (do odpowiedzi pod sygnałem i w state.json).

Wynik sygnału = pipsy do najwyższego trafionego TP (zamknięcie na BE po TP niczego nie odejmuje),
a gdy żadnego TP nie było - pipsy z SL / zamknięcia. Każda zmiana wyniku trafia do rec["pip_log"]
jako [czas UTC, przyrost], więc sygnał rozliczony w dwa dni liczy się do obu dni po kawałku.
"""
from __future__ import annotations

import pandas as pd


def book_exit(rec: dict, name: str, pips: float, when: pd.Timestamp) -> None:
    """Zapisz wynik po wyjściu (TPk / sl / timeout) do dziennika pipsów sygnału."""
    best = rec.get("pips")
    if name.startswith("tp") or name == "rev" or name.startswith("ai"):
        # najdalszy TP albo zamknięcie przez AI - liczy się to, co dalej od wejścia
        new = pips if best is None else max(best, pips)
    elif rec.get("tp_hit"):
        return                      # po TP: BE / zamknięcie nie zmienia wyniku
    else:
        new = pips
    if name.startswith("tp"):
        rec["tp_hit"] = int(name[2:])
    elif name == "sl":
        rec["sl_hit"] = True
    elif name == "rev" or name.startswith("ai"):
        rec["ai_exit"] = True
    delta = new - (best or 0.0)
    rec["pips"] = new
    if abs(delta) >= 0.05:
        rec.setdefault("pip_log", []).append([pd.Timestamp(when).isoformat(), round(delta, 1)])
