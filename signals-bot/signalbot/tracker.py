"""Rozliczanie sygnałów (TP / SL / zamknięcie po czasie) i zapis stanu."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

MAX_HOLD_BARS = 96  # 96 x M30 = 2 dni; potem zamykamy po cenie rynkowej


@dataclass
class Result:
    outcome: str      # tp / sl / timeout
    exit_price: float
    exit_time: pd.Timestamp
    r: float          # wynik w R (wielokrotność ryzyka)


def evaluate(bars_after: pd.DataFrame, direction: str, entry: float, sl: float, tp: float,
             max_hold: int = MAX_HOLD_BARS) -> Result | None:
    """bars_after = świece PO świecy wejścia. None = pozycja wciąż otwarta."""
    risk = abs(sl - entry)
    sign = -1 if direction == "SELL" else 1
    for i, row in enumerate(bars_after.itertuples(index=False)):
        if direction == "SELL":
            hit_sl, hit_tp = row.high >= sl, row.low <= tp
        else:
            hit_sl, hit_tp = row.low <= sl, row.high >= tp
        if hit_sl:  # gdy oba w jednej świecy, liczymy konserwatywnie SL
            return Result("sl", sl, row.time, -1.0)
        if hit_tp:
            return Result("tp", tp, row.time, sign * (tp - entry) / risk)
        if i + 1 >= max_hold:
            return Result("timeout", row.close, row.time, sign * (row.close - entry) / risk)
    return None


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"signals": {}}

    @property
    def signals(self) -> dict:
        return self.data["signals"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str))
        tmp.replace(self.path)
