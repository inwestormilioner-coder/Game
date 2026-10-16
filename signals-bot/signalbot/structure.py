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


@dataclass(frozen=True)
class VolumeProfile:
    edges: np.ndarray    # granice przedziałów cenowych (bins + 1)
    volume: np.ndarray   # wolumen w każdym przedziale
    poc: float           # cena z największym wolumenem
    val: float           # dół Value Area (70% wolumenu)
    vah: float           # góra Value Area

    def hvn_ranges(self, pct: float = 80) -> list[tuple[float, float]]:
        """Przedziały o wysokim wolumenie (High Volume Nodes)."""
        thr = np.percentile(self.volume, pct)
        return [(self.edges[i], self.edges[i + 1]) for i in np.flatnonzero(self.volume >= thr)]


def volume_profile(df: pd.DataFrame, end: int, lookback: int = 200, bins: int = 50) -> VolumeProfile | None:
    """Profil wolumenu ze świec [end-lookback, end]. Wolumen każdej świecy rozkładany
    równo na jej zakres high-low. None, gdy dane nie mają wolumenu."""
    if "volume" not in df.columns:
        return None
    w = df.iloc[max(0, end - lookback + 1) : end + 1]
    if w["volume"].sum() <= 0:
        return None
    lo, hi = float(w["low"].min()), float(w["high"].max())
    edges = np.linspace(lo, hi, bins + 1)
    vol = np.zeros(bins)
    for bl, bh, v in zip(w["low"].to_numpy(), w["high"].to_numpy(), w["volume"].to_numpy()):
        overlap = np.clip(np.minimum(edges[1:], bh) - np.maximum(edges[:-1], bl), 0, None)
        span = bh - bl
        vol += v * overlap / span if span > 0 else v * ((edges[:-1] <= bl) & (bl <= edges[1:]))
    poc_i = int(np.argmax(vol))
    # Value Area: rozszerzaj od POC w stronę większego wolumenu, aż do 70%
    lo_i = hi_i = poc_i
    total, acc = vol.sum(), vol[poc_i]
    while acc < 0.7 * total and (lo_i > 0 or hi_i < bins - 1):
        down = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if up >= down:
            hi_i += 1
            acc += vol[hi_i]
        else:
            lo_i -= 1
            acc += vol[lo_i]
    return VolumeProfile(edges, vol, float((edges[poc_i] + edges[poc_i + 1]) / 2),
                         float(edges[lo_i]), float(edges[hi_i + 1]))
