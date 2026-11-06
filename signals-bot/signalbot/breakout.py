"""Breakout + retest (BUY; SELL to lustro na zanegowanych cenach).

1. Poziom = ostatni potwierdzony swing high.
2. Wybicie: świeca zamyka się nad poziomem (opcjonalnie z korpusem >= `min_body_atr` x ATR).
3. Retest: w ciągu `max_wait` świec cena wraca do poziomu (low <= poziom + `tol_atr` x ATR)
   i zamyka się nad nim. Zamknięcie pod poziomem - `fail_atr` x ATR = nieudane wybicie, koniec.
4. Wejście: BUY STOP nad szczytem świecy retestu, ważne `entry_wait` świec.
   SL pod dołkiem retestu (i pod poziomem) - `sl_buf_atr` x ATR.
5. TP: wielokrotności ryzyka (`tps_r`), częściami, SL na wejście po TP1 - jak w sygnałach bota.
Filtr kierunku: EMA (`ema_len`) - BUY tylko, gdy wybicie zamyka się nad EMA.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .fibzone import FibParams, _atr, _simulate
from .structure import find_swings


@dataclass
class BrkParams:
    swing_n: int = 3
    min_body_atr: float = 0.0
    tol_atr: float = 0.25
    fail_atr: float = 0.3
    max_wait: int = 12
    entry_wait: int = 3
    sl_buf_atr: float = 0.2
    min_risk: float = 3.0
    tps_r: tuple = (1.0, 2.0, 3.0)
    be_after: int | None = 0
    max_hold: int = 96
    ema_len: int = 0
    ema_slope: int = 0


@dataclass
class BrkTrade:
    direction: str
    entry_idx: int
    entry: float
    sl: float
    r: float
    exits: list
    closed: bool

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)


def _scan_buy(df: pd.DataFrame, p: BrkParams) -> list[BrkTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = _atr(h, l, c)
    ema = pd.Series(c).ewm(span=p.ema_len, adjust=False).mean().to_numpy() if p.ema_len else None
    highs, _ = find_swings(df, p.swing_n)
    conf = [s.confirmed_at for s in highs]
    fp = FibParams(fractions=tuple(1 / len(p.tps_r) for _ in p.tps_r), be_after=p.be_after, max_hold=p.max_hold)
    out: list[BrkTrade] = []
    used: set[int] = set()
    j, t, busy = 0, 1, -1
    while t < n:
        while j < len(conf) and conf[j] <= t - 1:
            j += 1
        lvl_s = highs[j - 1] if j else None
        if t <= busy or lvl_s is None or lvl_s.idx in used or c[t] <= lvl_s.price:
            t += 1
            continue
        used.add(lvl_s.idx)
        lvl = lvl_s.price
        body_ok = abs(c[t] - o[t]) >= p.min_body_atr * a[t]
        trend_ok = ema is None or (c[t] > ema[t] and (not p.ema_slope or ema[t] > ema[max(0, t - p.ema_slope)]))
        if not (body_ok and trend_ok):
            t += 1
            continue
        # retest
        trade = None
        for u in range(t + 1, min(n, t + 1 + p.max_wait)):
            if c[u] < lvl - p.fail_atr * a[u]:
                break
            if l[u] <= lvl + p.tol_atr * a[u] and c[u] > lvl:
                stop = h[u] + 0.01
                sl = min(l[u], lvl) - p.sl_buf_atr * a[u]
                if stop - sl < p.min_risk:
                    break
                for v in range(u + 1, min(n, u + 1 + p.entry_wait)):
                    if h[v] >= stop:
                        entry = max(o[v], stop)
                        risk = entry - sl
                        levels = [entry + r * risk for r in p.tps_r]
                        if l[v] <= sl:
                            r, exits, closed = -1.0, [("sl", v, sl, 1.0)], True
                        else:
                            r, exits, closed = _simulate(h, l, c, v, entry, sl, levels, fp)
                        trade = BrkTrade("BUY", v, entry, sl, r, exits, closed)
                        break
                    if l[v] <= sl:
                        break
                break
        if trade:
            out.append(trade)
            busy = trade.exits[-1][1] if trade.closed else n
        t += 1
    return out


def find_brk_trades(df: pd.DataFrame, p: BrkParams) -> list[BrkTrade]:
    df = df.reset_index(drop=True)
    buys = _scan_buy(df, p)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    sells = _scan_buy(m, p)
    for s in sells:
        s.direction = "SELL"
        s.entry, s.sl = -s.entry, -s.sl
    return sorted(buys + sells, key=lambda x: x.entry_idx)
