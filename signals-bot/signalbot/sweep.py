"""Liquidity sweep + reclaim (BUY; SELL to lustro na zanegowanych cenach).

Pod lokalnym dołkiem leżą stop lossy kupujących. Gdy świeca wybije pod ostatni potwierdzony swing low
(zbierze płynność) i zamknie się z powrotem nad nim, wchodzimy w drugą stronę.

1. Sweep: low < swing low - `min_depth_atr` x ATR, zamknięcie > swing low (opcjonalnie dolny knot
   >= `min_wick` korpusu). Każdy dołek można zebrać tylko raz.
2. Wejście: `entry` = "close" (rynkowo na otwarciu następnej świecy) albo "stop" (BUY STOP nad szczytem
   świecy sweepu, ważny `entry_wait` świec).
3. SL: pod knotem sweepu - `sl_buf_atr` x ATR.
4. TP: R-krotności częściami z BE po TP1 (`tps_r`) albo "liquidity": najbliższy swing high nad ceną.
Opcja `equal_lows`: dołek musi być podwójny (dwa swing lows w odległości <= `eq_tol_atr` x ATR).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .breakout import BrkTrade
from .fibzone import FibParams, _atr, _simulate
from .structure import find_swings


@dataclass
class SweepParams:
    swing_n: int = 3
    lookback: int = 3                 # ile ostatnich swing lows może zostać zebranych
    min_depth_atr: float = 0.05
    min_wick: float = 0.0             # dolny knot / korpus
    entry: str = "close"              # close | stop
    entry_wait: int = 3
    sl_buf_atr: float = 0.1
    min_risk: float = 3.0
    tps_r: tuple = (1.0, 2.0, 3.0)
    be_after: int | None = 0
    tp_mode: str = "rr"               # rr | liquidity
    min_rr: float = 1.5
    max_hold: int = 96
    equal_lows: bool = False
    eq_tol_atr: float = 0.3
    ema_len: int = 0


def _scan_buy(df: pd.DataFrame, p: SweepParams) -> list[BrkTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(c)
    a = _atr(h, l, c)
    ema = pd.Series(c).ewm(span=p.ema_len, adjust=False).mean().to_numpy() if p.ema_len else None
    highs, lows = find_swings(df, p.swing_n)
    out: list[BrkTrade] = []
    used: set[int] = set()
    busy = -1
    for t in range(1, n - 1):
        if t <= busy:
            continue
        known = [s for s in lows if s.confirmed_at <= t - 1][-p.lookback:]
        target = None
        for s in reversed(known):
            if s.idx in used:
                continue
            if p.equal_lows and not any(o2.idx != s.idx and abs(o2.price - s.price) <= p.eq_tol_atr * a[t]
                                        for o2 in known):
                continue
            if l[t] < s.price - p.min_depth_atr * a[t] and c[t] > s.price:
                target = s
                break
        if target is None:
            continue
        used.add(target.idx)
        body = abs(c[t] - o[t]) or 1e-9
        if (min(o[t], c[t]) - l[t]) / body < p.min_wick:
            continue
        if ema is not None and c[t] <= ema[t]:
            continue
        sl = l[t] - p.sl_buf_atr * a[t]
        if p.entry == "close":
            v, entry = t + 1, o[t + 1]
        else:
            stop, v = h[t] + 0.01, None
            for u in range(t + 1, min(n, t + 1 + p.entry_wait)):
                if l[u] <= sl:
                    break
                if h[u] >= stop:
                    v, entry = u, max(o[u], stop)
                    break
            if v is None:
                continue
        risk = entry - sl
        if risk < p.min_risk:
            continue
        if p.tp_mode == "liquidity":
            above = [s.price for s in highs if s.confirmed_at <= t and s.price > entry]
            if not above or (min(above) - entry) / risk < p.min_rr:
                continue
            levels, fp = [min(above)], FibParams(fractions=(1.0,), be_after=None, max_hold=p.max_hold)
        else:
            levels = [entry + r * risk for r in p.tps_r]
            fp = FibParams(fractions=tuple(1 / len(levels) for _ in levels), be_after=p.be_after,
                           max_hold=p.max_hold)
        if l[v] <= sl:
            r, exits, closed = -1.0, [("sl", v, sl, 1.0)], True
        else:
            r, exits, closed = _simulate(h, l, c, v, entry, sl, levels, fp)
        out.append(BrkTrade("BUY", v, entry, sl, r, exits, closed))
        busy = exits[-1][1] if closed else n
    return out


def find_sweep_trades(df: pd.DataFrame, p: SweepParams) -> list[BrkTrade]:
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
