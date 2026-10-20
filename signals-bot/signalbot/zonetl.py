"""Strategia "BOS + powrót do strefy + linia trendu" (SELL; BUY to lustro).

Jak na wykresie z TPZ: po spadkowym BOS cena wraca do strefy podaży (order block), w tym samym
miejscu jest opadająca linia trendu - odrzucenie i sprzedaż.

1. Strefa podaży: przy zamknięciu pod ostatnim swing low (BOS w dół) - świeca z najwyższym szczytem
   między tym swing low a przebiciem (order block, zakres high-low). Znika po zamknięciu nad strefą.
2. Linia oporu jak w TrendLineSample: najwyższy szczyt w [short+1, long] świec wstecz -> najwyższy
   w [1, short]; musi opadać i na bieżącej świecy przechodzić przez strefę (± `tl_tol_atr` ATR).
3. Sygnał: świeca dotyka strefy (high >= dół strefy) i zamyka się spadkowo POD strefą.
   Wejście po cenie zamknięcia, SL nad strefą / szczytem dotknięcia + bufor, TP na płynności
   (najbliższy swing low pod ceną) albo stałe RR.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .structure import find_swings


@dataclass
class ZtlParams:
    swing_n: int = 3
    require_tl: bool = True
    tl_short: int = 30
    tl_long: int = 100
    tl_tol_atr: float = 0.5
    sl_buffer_atr: float = 0.15
    tp_mode: str = "liquidity"     # liquidity | rr
    rr: float = 2.0
    min_rr: float = 1.5
    min_risk: float = 0.0
    max_zone_age: int = 200        # strefa ważna przez tyle świec
    max_hold: int = 192


@dataclass
class ZtlTrade:
    direction: str
    entry_idx: int
    entry: float
    sl: float
    tp: float
    zone_bot: float
    zone_top: float
    r: float = 0.0
    outcome: str = "open"
    exit_idx: int = -1
    closed: bool = False


def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _resistance_at(h: np.ndarray, t: int, short: int, long: int) -> tuple[float, float] | None:
    """(cena linii na świecy t, nachylenie) z danych do t-1."""
    if t - long < 0:
        return None
    x2 = t - short + int(np.argmax(h[t - short : t]))
    x1 = t - long + int(np.argmax(h[t - long : t - short]))
    k = (h[x2] - h[x1]) / (x2 - x1)
    return h[x1] + k * (t - x1), k


def _scan_sell(df: pd.DataFrame, p: ZtlParams) -> list[ZtlTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(df)
    a = _atr(h, l, c)
    highs, lows = find_swings(df, p.swing_n)
    low_conf = [s.confirmed_at for s in lows]
    zones: list[list] = []            # [bot, top, created]
    used: set[int] = set()
    out: list[ZtlTrade] = []
    busy_until = -1
    j = 0
    for t in range(1, n):
        while j < len(low_conf) and low_conf[j] <= t - 1:
            j += 1
        last_sl = lows[j - 1] if j else None
        # BOS w dół -> nowa strefa podaży
        if last_sl is not None and last_sl.idx not in used and c[t] < last_sl.price:
            used.add(last_sl.idx)
            ob = last_sl.idx + int(np.argmax(h[last_sl.idx : t + 1]))
            zones.append([l[ob], h[ob], t])
        zones = [z for z in zones if not (t > z[2] and c[t] > z[1]) and t - z[2] <= p.max_zone_age]
        if t <= busy_until:
            continue
        for z in zones:
            bot, top, made = z
            if t <= made or not (h[t] >= bot and c[t] < bot and c[t] < o[t]):
                continue
            if p.require_tl:
                res = _resistance_at(h, t, p.tl_short, p.tl_long)
                if res is None:
                    break
                y, k = res
                if k >= 0 or not (bot - p.tl_tol_atr * a[t] <= y <= top + p.tl_tol_atr * a[t]):
                    continue
            entry = c[t]
            sl = max(top, h[t]) + p.sl_buffer_atr * a[t]
            risk = sl - entry
            if risk <= 0 or risk < p.min_risk:
                continue
            if p.tp_mode == "liquidity":
                below = [s.price for s in lows if s.confirmed_at <= t and s.price < entry]
                tp = max(below) if below else entry - p.rr * risk
                if (entry - tp) / risk < p.min_rr:
                    continue
            else:
                tp = entry - p.rr * risk
            tr = ZtlTrade("SELL", t, entry, sl, tp, bot, top)
            for u in range(t + 1, min(n, t + 1 + p.max_hold)):
                if h[u] >= sl:
                    tr.outcome, tr.r, tr.exit_idx, tr.closed = "sl", -1.0, u, True
                    break
                if l[u] <= tp:
                    tr.outcome, tr.r, tr.exit_idx, tr.closed = "tp", (entry - tp) / risk, u, True
                    break
            else:
                if n >= t + 1 + p.max_hold:
                    last = t + p.max_hold
                    tr.outcome, tr.r, tr.exit_idx, tr.closed = "timeout", (entry - c[last]) / risk, last, True
            out.append(tr)
            zones = [x for x in zones if x is not z]
            busy_until = tr.exit_idx if tr.closed else n
            break
    return out


def find_ztl_trades(df: pd.DataFrame, p: ZtlParams | None = None) -> list[ZtlTrade]:
    p = p or ZtlParams()
    df = df.reset_index(drop=True)
    sells = _scan_sell(df, p)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    buys = _scan_sell(m, p)
    for b in buys:
        b.direction = "BUY"
        b.entry, b.sl, b.tp = -b.entry, -b.sl, -b.tp
        b.zone_bot, b.zone_top = -b.zone_top, -b.zone_bot
    return sorted(sells + buys, key=lambda x: x.entry_idx)
