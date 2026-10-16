"""Strategia "odbicie od strefy + Fibo" (BUY; SELL to lustro na zanegowanych cenach).

Strefy jak we wskaźniku tpz_zones.pine: order block = świeca z najniższym dołkiem między
swing high a świecą, która go przebiła (BOS w górę). Strefa znika po zamknięciu pod nią.

Setup:
1. Cena dotyka strefy (low <= góra strefy).
2. Fibo: 1 = ostatni potwierdzony swing high (szczyt spadku do strefy), 0 = najniższy dołek od dotknięcia.
3. Zlecenie BUY STOP na 0.1272, SL na -0.1272 (ryzyko = 0.2544 zakresu Fibo).
   Każdy nowy dołek przesuwa 0, więc i zlecenie; świeca z nowym dołkiem nie może otworzyć pozycji.
4. TP na kolejnych poziomach Fibo — jednym albo częściami (scale-out), opcjonalnie SL na wejście po TP n.
5. Anulowanie: zamknięcie pod strefą albo brak wejścia przez `max_wait` świec.

Filtr linii trendu (opcjonalny, jak skrypt TrendLineSample): linia wsparcia z najniższego dołka
w [short+1, long] świec wstecz do najniższego dołka w [1, short]; BUY tylko gdy linia rośnie.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .structure import find_swings

FIB_TPS = (0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 1.0, 1.272, 1.618)


@dataclass
class FibParams:
    swing_n: int = 3
    entry_fib: float = 0.1272
    sl_fib: float = -0.1272
    tps: tuple[float, ...] = (1.0,)          # poziomy TP
    fractions: tuple[float, ...] = (1.0,)    # jaka część pozycji na każdym TP
    be_after: int | None = None              # po którym TP (indeks od 0) SL na wejście
    max_wait: int = 24                       # świec od dotknięcia strefy na wejście
    max_hold: int = 96
    min_range_atr: float = 1.0               # minimalny zakres Fibo (1 - 0) w ATR
    trend_filter: bool = False
    tl_short: int = 30
    tl_long: int = 100


@dataclass
class FibTrade:
    direction: str
    touch_idx: int
    entry_idx: int
    fib0: float
    fib1: float
    entry: float
    sl: float
    r: float = 0.0
    exits: list = field(default_factory=list)
    zone_bot: float = 0.0
    zone_top: float = 0.0
    fib1_idx: int = 0


def _atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _support_slope(l: np.ndarray, t: int, short: int, long: int) -> float | None:
    """Nachylenie linii wsparcia na świecy t (tylko dane do t-1, jak w skrypcie)."""
    if t - long < 0:
        return None
    near = l[t - short : t]                 # 1..short świec wstecz
    far = l[t - long : t - short]           # short+1..long świec wstecz
    x2 = t - short + int(np.argmin(near))
    x1 = t - long + int(np.argmin(far))
    return (l[x2] - l[x1]) / (x2 - x1)


def _simulate(h, l, c, start: int, entry: float, sl: float, levels: list[float],
              p: FibParams) -> tuple[float, list]:
    """Zarządzanie pozycją BUY od świecy wejścia. Zwraca wynik w R i listę wyjść."""
    risk = entry - sl
    left, cur_sl, pnl, k, exits = 1.0, sl, 0.0, 0, []
    for u in range(start, min(len(c), start + p.max_hold)):
        if u > start and l[u] <= cur_sl:     # SL przed TP (konserwatywnie)
            pnl += left * (cur_sl - entry)
            exits.append(("sl", u, cur_sl, left))
            return pnl / risk, exits
        while k < len(levels) and h[u] >= levels[k]:
            frac = min(p.fractions[k], left)
            pnl += frac * (levels[k] - entry)
            left -= frac
            exits.append((f"tp{k + 1}", u, levels[k], frac))
            if p.be_after is not None and k == p.be_after:
                cur_sl = entry
            k += 1
            if left <= 1e-9:
                return pnl / risk, exits
    last = min(len(c), start + p.max_hold) - 1
    pnl += left * (c[last] - entry)
    exits.append(("timeout", last, c[last], left))
    return pnl / risk, exits


def _scan_buy(df: pd.DataFrame, p: FibParams) -> list[FibTrade]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    a = _atr(h, l, c)
    swing_highs, _ = find_swings(df, p.swing_n)
    conf = [s.confirmed_at for s in swing_highs]
    trades: list[FibTrade] = []
    zones: list[list] = []        # [bot, top, created]
    used: set[int] = set()
    setup = None
    busy_until = -1               # jedna pozycja naraz

    j = 0
    for t in range(1, len(df)):
        while j < len(conf) and conf[j] <= t - 1:
            j += 1
        last_sh = swing_highs[j - 1] if j else None

        # nowe strefy: przebicie ostatniego swing high
        if last_sh is not None and last_sh.idx not in used and c[t] > last_sh.price:
            used.add(last_sh.idx)
            ob = last_sh.idx + int(np.argmin(l[last_sh.idx : t + 1]))
            zones.append([l[ob], h[ob], t])

        # unieważnienie stref
        zones = [z for z in zones if not (t > z[2] and c[t] < z[0])]

        if setup is not None:
            z = setup["zone"]
            if c[t] < z[0] or t - setup["touch"] > p.max_wait:
                setup = None
            elif l[t] < setup["f0"]:
                setup["f0"] = l[t]
            else:
                f0, f1 = setup["f0"], setup["f1"]
                rng = f1 - f0
                stop = f0 + p.entry_fib * rng
                if rng >= p.min_range_atr * a[t] and h[t] >= stop:
                    entry = max(o[t], stop)
                    sl = f0 + p.sl_fib * rng
                    levels = [f0 + x * rng for x in p.tps]
                    levels = [x for x in levels if x > entry]
                    if levels:
                        r, exits = _simulate(h, l, c, t, entry, sl, levels,
                                             FibParams(**{**p.__dict__, "fractions": p.fractions[-len(levels):]}))
                        trades.append(FibTrade("BUY", setup["touch"], t, f0, f1, entry, sl, r, exits,
                                               z[0], z[1], setup["f1_idx"]))
                        busy_until = exits[-1][1]
                        zones = [x for x in zones if x is not z]
                    setup = None
            continue

        if t <= busy_until or last_sh is None:
            continue
        for z in zones:
            if t > z[2] and l[t] <= z[1] and last_sh.price > z[1]:
                if p.trend_filter:
                    slope = _support_slope(l, t, p.tl_short, p.tl_long)
                    if slope is None or slope <= 0:
                        break
                setup = {"zone": z, "touch": t, "f0": l[t], "f1": last_sh.price, "f1_idx": last_sh.idx}
                break
    return trades


def find_fib_trades(df: pd.DataFrame, p: FibParams | None = None) -> list[FibTrade]:
    p = p or FibParams()
    df = df.reset_index(drop=True)
    buys = _scan_buy(df, p)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    sells = _scan_buy(m, p)
    for s in sells:
        s.direction = "SELL"
        s.fib0, s.fib1, s.entry, s.sl = -s.fib0, -s.fib1, -s.entry, -s.sl
        s.exits = [(n, i, -px, f) for n, i, px, f in s.exits]
        s.zone_bot, s.zone_top = -s.zone_top, -s.zone_bot
    return sorted(buys + sells, key=lambda x: x.entry_idx)
