"""Struktura rynku: ATR, swing high / swing low (fraktale)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Swing:
    idx: int          # indeks świecy, na której jest szczyt/dołek
    price: float
    confirmed_at: int  # od tej świecy (włącznie) swing jest znany bez zaglądania w przyszłość


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def find_swings(df: pd.DataFrame, n: int = 3) -> tuple[list[Swing], list[Swing]]:
    """Fraktal: high[i] jest najwyższy w oknie i-n..i+n (analogicznie low).

    Swing jest potwierdzony dopiero na świecy i+n, więc detektor nie używa przyszłych danych.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    sh: list[Swing] = []
    sl: list[Swing] = []
    for i in range(n, len(df) - n):
        win_h = highs[i - n : i + n + 1]
        win_l = lows[i - n : i + n + 1]
        if highs[i] == win_h.max() and np.argmax(win_h) == n:
            sh.append(Swing(i, float(highs[i]), i + n))
        if lows[i] == win_l.min() and np.argmin(win_l) == n:
            sl.append(Swing(i, float(lows[i]), i + n))
    return sh, sl


def confirmed_before(swings: list[Swing], t: int) -> list[Swing]:
    return [s for s in swings if s.confirmed_at <= t]
