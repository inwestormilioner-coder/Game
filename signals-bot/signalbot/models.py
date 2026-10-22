"""Modele wejścia ICT (BUY; SELL to lustro na zanegowanych cenach).

Wspólny początek: Liquidity Sweep - cena wybija pod ostatni potwierdzony swing low.
MSS (Market Structure Shift) - w ciągu `mss_window` świec zamknięcie nad ostatnim swing high sprzed sweepu.

Strefy wejścia (zlecenie limit na górnej krawędzi strefy, SL pod dołkiem sweepu, TP na płynności):
  fvg   - bycza luka FVG w impulsie od dołka sweepu do MSS                       (model 1)
  bpr   - Balanced Price Range: część wspólna spadkowej FVG (przed sweepem)
          i wzrostowej FVG (po sweepie), bez wymogu MSS                          (model 2)
  ifvg  - Inverted FVG: spadkowa FVG ze spadku, nad którą MSS zamknął cenę        (model 3, sweep zamiast SMT)
  bb    - Breaker Block: ostatnia wzrostowa świeca przy przebitym swing high      (model 4, sweep zamiast SMT)
  bbfvg - Breaker Block pokrywający się z FVG impulsu                            (model 5)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .structure import find_swings


@dataclass
class ModelParams:
    model: str = "fvg"
    swing_n: int = 3
    mss_window: int = 20
    sl_buffer_atr: float = 0.15
    tp_mode: str = "liquidity"      # liquidity | rr
    rr: float = 2.0
    min_rr: float = 1.5
    min_risk: float = 3.0
    max_wait: int = 48
    max_hold: int = 192


@dataclass
class ModelTrade:
    direction: str
    place_idx: int
    entry_idx: int
    entry: float
    sl: float
    tp: float
    zone: tuple
    r: float = 0.0
    outcome: str = "open"
    exit_idx: int = -1
    closed: bool = False


def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _bull_fvgs(h, l, a, b):
    """Byczy FVG ze środkową świecą k w [a, b]: (bot, top, znane_od)."""
    return [(h[k - 1], l[k + 1], k + 1) for k in range(max(a, 1), min(b, len(h) - 2) + 1) if l[k + 1] > h[k - 1]]


def _bear_fvgs(h, l, a, b):
    return [(h[k + 1], l[k - 1], k + 1) for k in range(max(a, 1), min(b, len(h) - 2) + 1) if h[k + 1] < l[k - 1]]


def _zone(model, o, h, l, c, hi_s, sweep_i, low_i, m):
    """(dół, góra, znana_od) strefy wejścia albo None."""
    if model == "bpr":
        bears = _bear_fvgs(h, l, hi_s.idx, low_i)
        end = sweep_i + 20
        for bot, top, known in _bull_fvgs(h, l, low_i + 1, end):
            for b_bot, b_top, _ in bears:
                lo, hi = max(bot, b_bot), min(top, b_top)
                if hi > lo:
                    return lo, hi, known
        return None
    if m is None:
        return None
    if model == "fvg":
        f = [z for z in _bull_fvgs(h, l, low_i + 1, m) if z[2] <= m + 1]
        return (f[-1][0], f[-1][1], max(m, f[-1][2])) if f else None
    if model == "ifvg":
        f = [z for z in _bear_fvgs(h, l, hi_s.idx, low_i) if z[1] < c[m]]
        return (f[-1][0], f[-1][1], m) if f else None
    # breaker: ostatnia wzrostowa świeca przy przebitym swing high
    j = next((x for x in range(hi_s.idx, max(-1, hi_s.idx - 6), -1) if c[x] > o[x]), None)
    if j is None:
        return None
    bb = (l[j], h[j], m)
    if model == "bb":
        return bb
    if model == "bbfvg":
        for bot, top, known in _bull_fvgs(h, l, low_i + 1, m):
            lo, hi = max(bot, bb[0]), min(top, bb[1])
            if hi > lo:
                return lo, hi, max(m, known)
    return None


def _scan_buy(df: pd.DataFrame, p: ModelParams) -> list[ModelTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(df)
    a = _atr(h, l, c)
    highs, lows = find_swings(df, p.swing_n)
    out: list[ModelTrade] = []
    used: set[int] = set()
    busy_until = -1
    for t in range(1, n):
        if t <= busy_until:
            continue
        known_lows = [s for s in lows if s.confirmed_at <= t - 1]
        if not known_lows:
            continue
        lo_s = known_lows[-1]
        if lo_s.idx in used or l[t] >= lo_s.price:
            continue
        used.add(lo_s.idx)                                   # sweep płynności pod swing low
        known_highs = [s for s in highs if s.confirmed_at <= t and s.idx < t]
        if not known_highs:
            continue
        hi_s = known_highs[-1]
        # MSS: zamknięcie nad hi_s; dołek sweepu = najniższy low do MSS
        m, low_i = None, t
        for u in range(t, min(n, t + p.mss_window + 1)):
            if l[u] < l[low_i]:
                low_i = u
            if c[u] > hi_s.price:
                m = u
                break
        z = _zone(p.model, o, h, l, c, hi_s, t, low_i, m)
        if z is None:
            continue
        bot, top, known = z
        entry = top
        sweep_low = float(l[low_i: known + 1].min())
        sl = sweep_low - p.sl_buffer_atr * a[known]
        risk = entry - sl
        if known >= n or risk <= 0 or risk < p.min_risk or c[known] <= entry:
            continue
        if p.tp_mode == "liquidity":
            above = [s.price for s in highs if s.confirmed_at <= known and s.price > c[known]]
            tp = min(above) if above else None
            if tp is None or (tp - entry) / risk < p.min_rr:
                continue
        else:
            tp = entry + p.rr * risk
        # zlecenie limit od świecy known+1
        for u in range(known + 1, min(n, known + 1 + p.max_wait)):
            if l[u] <= entry:
                fill = min(o[u], entry)
                tr = ModelTrade("BUY", known, u, fill, sl, tp, (bot, top))
                risk_f = fill - sl
                for v in range(u, min(n, u + p.max_hold)):
                    if l[v] <= sl:
                        tr.outcome, tr.r, tr.exit_idx, tr.closed = "sl", -1.0, v, True
                        break
                    if v > u and h[v] >= tp:
                        tr.outcome, tr.r, tr.exit_idx, tr.closed = "tp", (tp - fill) / risk_f, v, True
                        break
                else:
                    if n >= u + p.max_hold:
                        last = u + p.max_hold - 1
                        tr.outcome, tr.r, tr.exit_idx, tr.closed = "timeout", (c[last] - fill) / risk_f, last, True
                out.append(tr)
                busy_until = tr.exit_idx if tr.closed else n
                break
            if h[u] >= tp or c[u] < sweep_low:
                break
    return out


def find_model_trades(df: pd.DataFrame, p: ModelParams) -> list[ModelTrade]:
    df = df.reset_index(drop=True)
    buys = _scan_buy(df, p)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    sells = _scan_buy(m, p)
    for s in sells:
        s.direction = "SELL"
        s.entry, s.sl, s.tp = -s.entry, -s.sl, -s.tp
        s.zone = (-s.zone[1], -s.zone[0])
    return sorted(buys + sells, key=lambda x: x.entry_idx)
