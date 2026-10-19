"""Strategia "Liquidity + FVG + BOS" (BUY; SELL to lustro na zanegowanych cenach).

1. BOS + FVG: impuls zamyka się nad ostatnim swing high i zostawia lukę FVG
   (low świecy k+1 > high świecy k-1). FVG = strefa [high[k-1], low[k+1]].
2. Liquidity: po powstaniu FVG tworzy się swing low NAD luką - tam leżą stop lossy (SSL).
3. Zlecenie BUY LIMIT na górze FVG (albo w połowie), wystawione z wyprzedzeniem.
   Żeby cena do niego doszła, musi najpierw zebrać tę płynność.
4. SL pod całym FVG (ważny poziom) + bufor, TP na najbliższej płynności nad ceną (BSL)
   albo stałe RR.
5. Anulowanie: zamknięcie pod FVG, cena doszła do TP przed wejściem albo minęło `max_wait` świec.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .structure import find_swings


@dataclass
class IctParams:
    swing_n: int = 3
    min_gap_atr: float = 0.3      # minimalna wysokość FVG w ATR
    bos_window: int = 3           # impuls musi przebić swing high w ciągu tylu świec od FVG
    require_bos: bool = True
    require_liq: bool = True
    liq_max_atr: float = 4.0      # płynność nie dalej niż tyle ATR nad FVG
    entry: str = "top"            # top | mid  (krawędź albo połowa FVG)
    sl_buffer_atr: float = 0.15
    tp_mode: str = "liquidity"    # liquidity | rr
    rr: float = 2.0               # dla tp_mode="rr" (i minimalne RR dla liquidity = min_rr)
    min_rr: float = 1.5
    min_risk: float = 0.0         # minimalny SL w cenie
    max_wait: int = 96            # ile świec zlecenie czeka na wejście
    max_hold: int = 192


@dataclass
class IctTrade:
    direction: str
    fvg_idx: int
    place_idx: int                # świeca, po której zlecenie może być wystawione (sygnał)
    entry_idx: int
    entry: float
    sl: float
    tp: float
    fvg_bot: float
    fvg_top: float
    liq: float | None
    r: float = 0.0
    outcome: str = "open"
    exit_idx: int = -1
    closed: bool = False
    extra: dict = field(default_factory=dict)


def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _scan_buy(df: pd.DataFrame, p: IctParams) -> list[IctTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(df)
    a = _atr(h, l, c)
    highs, lows = find_swings(df, p.swing_n)
    out: list[IctTrade] = []

    for k in range(2, n - 1):
        bot, top = h[k - 1], l[k + 1]
        if top - bot < p.min_gap_atr * a[k]:
            continue
        # BOS: w oknie impulsu zamknięcie nad ostatnim potwierdzonym swing high
        if p.require_bos:
            prev = [s for s in highs if s.confirmed_at <= k - 1]
            if not prev:
                continue
            lvl = prev[-1].price
            if not any(c[j] > lvl for j in range(k - 1, min(n, k + 1 + p.bos_window))):
                continue
        made = k + 1                                   # FVG znane po zamknięciu świecy k+1
        entry = top if p.entry == "top" else (top + bot) / 2
        sl = bot - p.sl_buffer_atr * a[made]
        risk = entry - sl
        if risk <= 0 or risk < p.min_risk:
            continue

        placed = None
        liq = None
        for t in range(made + 1, min(n, made + 1 + p.max_wait)):
            if c[t] < bot:                             # FVG przebite - koniec
                break
            if placed is None:
                # płynność: swing low nad FVG, powstały po FVG, znany do świecy t-1
                cand = [s for s in lows if s.idx > made and s.confirmed_at <= t - 1
                        and top < s.price <= top + p.liq_max_atr * a[made]]
                if p.require_liq and not cand:
                    continue
                liq = cand[-1].price if cand else None
                if l[t] <= liq if liq is not None else False:
                    continue                           # płynność zebrana zanim wystawiliśmy zlecenie
                # TP
                if p.tp_mode == "liquidity":
                    above = [s.price for s in highs if s.confirmed_at <= t - 1 and s.price > c[t - 1]]
                    tp = min(above) if above else entry + p.rr * risk
                else:
                    tp = entry + p.rr * risk
                if (tp - entry) / risk < (p.min_rr if p.tp_mode == "liquidity" else 0):
                    break
                placed = t - 1                         # zlecenie wystawione po zamknięciu t-1
                out_tp = tp
            if h[t] >= out_tp and l[t] > entry:        # cena poszła do celu bez nas
                placed = None
                break
            if l[t] <= entry:                          # wejście
                fill = min(o[t], entry)
                tr = IctTrade("BUY", k, placed, t, fill, sl, out_tp, bot, top, liq)
                _manage(tr, h, l, c, t, p)
                out.append(tr)
                break
    return out


def _manage(tr: IctTrade, h, l, c, t: int, p: IctParams) -> None:
    risk = tr.entry - tr.sl
    end = t + p.max_hold
    for u in range(t, min(len(c), end)):
        if l[u] <= tr.sl:                              # SL przed TP (konserwatywnie)
            tr.outcome, tr.r, tr.exit_idx, tr.closed = "sl", -1.0, u, True
            return
        if u > t and h[u] >= tr.tp:
            tr.outcome, tr.r, tr.exit_idx, tr.closed = "tp", (tr.tp - tr.entry) / risk, u, True
            return
    if len(c) >= end:
        last = end - 1
        tr.outcome, tr.r, tr.exit_idx, tr.closed = "timeout", (c[last] - tr.entry) / risk, last, True


def find_ict_trades(df: pd.DataFrame, p: IctParams | None = None) -> list[IctTrade]:
    p = p or IctParams()
    df = df.reset_index(drop=True)
    buys = _scan_buy(df, p)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    sells = _scan_buy(m, p)
    for s in sells:
        s.direction = "SELL"
        s.entry, s.sl, s.tp = -s.entry, -s.sl, -s.tp
        s.fvg_bot, s.fvg_top = -s.fvg_top, -s.fvg_bot
        s.liq = -s.liq if s.liq is not None else None
    return sorted(buys + sells, key=lambda x: x.entry_idx)
