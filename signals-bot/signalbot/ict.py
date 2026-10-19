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
    sl_mode: str = "fvg"          # fvg = tuż za FVG | swing = za lokalnym dołkiem/szczytem (początek impulsu)
    tp_mode: str = "liquidity"    # liquidity | rr | fibext (Fibo impulsu: 1.0 / 1.272 / 1.618, BE po TP1)
    fib_tps: tuple = (1.0, 1.272, 1.618)
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
        made = k + 1                                   # FVG znane po zamknięciu świecy k+1
        # BOS: w oknie impulsu zamknięcie nad ostatnim potwierdzonym swing high;
        # zlecenie dopiero po świecy, na której BOS jest już znany
        if p.require_bos:
            prev = [s for s in highs if s.confirmed_at <= k - 1]
            if not prev:
                continue
            lvl = prev[-1].price
            bos = [j for j in range(k - 1, min(n, k + 1 + p.bos_window)) if c[j] > lvl]
            if not bos:
                continue
            made = max(made, bos[0])
        entry = top if p.entry == "top" else (top + bot) / 2
        below = [s.price for s in lows if s.confirmed_at <= made and s.price < bot]
        anchor = below[-1] if below else float(l[max(0, k - 10) : k + 1].min())
        imp_high = float(h[k - 1 : made + 1].max())
        if p.sl_mode == "swing":
            # lokalny dołek pod FVG, znany przy powstaniu luki (początek impulsu)
            sl = min(anchor, bot) - p.sl_buffer_atr * a[made]
        else:
            sl = bot - p.sl_buffer_atr * a[made]
        risk = entry - sl
        if risk <= 0 or risk < p.min_risk:
            continue

        placed = None                                   # świeca, po której zamknięciu wystawiono zlecenie
        liq = tp = None
        for t in range(made + 1, min(n, made + 1 + p.max_wait)):
            if placed is not None:
                # zlecenie już stoi: najpierw wejście (w trakcie świecy), potem anulowania po zamknięciu
                if l[t] <= entry:
                    fill = min(o[t], entry)
                    tr = IctTrade("BUY", k, placed, t, fill, sl, tp, bot, top, liq)
                    if p.tp_mode == "fibext":
                        _manage_partials(tr, h, l, c, t, p, fib_levels)
                    else:
                        _manage(tr, h, l, c, t, p)
                    out.append(tr)
                    break
                if h[t] >= tp or c[t] < bot:           # cel osiągnięty bez nas albo FVG przebite
                    break
                continue
            # zlecenia jeszcze nie ma: decyzja na podstawie danych do zamknięcia świecy t
            if c[t] < bot:
                break
            if c[t] <= entry:
                continue                               # cena już w FVG - limit byłby nad rynkiem
            cand = [s for s in lows if s.idx > made and s.confirmed_at <= t
                    and top < s.price <= top + p.liq_max_atr * a[made]]
            if p.require_liq and not cand:
                continue
            liq_s = cand[-1] if cand else None
            liq = liq_s.price if liq_s else None
            if liq_s is not None and l[liq_s.idx + 1 : t + 1].min(initial=np.inf) <= liq:
                continue                               # płynność już zebrana
            if p.tp_mode == "liquidity":
                above = [s.price for s in highs if s.confirmed_at <= t and s.price > c[t]]
                tp = min(above) if above else entry + p.rr * risk
                if (tp - entry) / risk < p.min_rr:
                    break
            elif p.tp_mode == "fibext":
                rng_i = imp_high - anchor
                fib_levels = [x for x in (anchor + f * rng_i for f in p.fib_tps) if x > entry]
                if not fib_levels or (fib_levels[-1] - entry) / risk < p.min_rr:
                    break
                tp = fib_levels[-1]
            else:
                tp = entry + p.rr * risk
            placed = t
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


def _manage_partials(tr: IctTrade, h, l, c, t: int, p: IctParams, levels: list[float]) -> None:
    """Częściowe TP na poziomach Fibo, SL na wejście po pierwszym TP. Świeca wejścia: SL sprawdzany pierwszy."""
    from .fibzone import FibParams, _simulate

    if l[t] <= tr.sl:
        tr.outcome, tr.r, tr.exit_idx, tr.closed = "sl", -1.0, t, True
        return
    fr = tuple(1 / len(levels) for _ in levels)
    r, exits, closed = _simulate(h, l, c, t, tr.entry, tr.sl, levels,
                                 FibParams(tps=tuple(levels), fractions=fr, be_after=0, max_hold=p.max_hold))
    tr.r, tr.closed = r, closed
    if exits:
        tr.outcome, tr.exit_idx = exits[-1][0], exits[-1][1]


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


# ───────────── Hybryda: kontekst ICT (płynność + FVG + BOS) + wejście/SL/TP z Fibo ─────────────

@dataclass
class IctFibParams:
    ict: IctParams = field(default_factory=IctParams)
    tps: tuple = (0.382, 0.618, 1.0, 1.272, 1.618)
    fractions: tuple = (0.2, 0.2, 0.2, 0.2, 0.2)
    be_after: int | None = 0                 # SL na wejście po TP1
    sl_mode: str = "fib"                     # fib = -0.1272 | swing = za lokalnym dołkiem pod FVG
    max_wait: int = 24                       # świec od zebrania płynności na wejście


def _scan_buy_ictfib(df: pd.DataFrame, q: IctFibParams) -> list[IctTrade]:
    from .fibzone import FibParams, _simulate

    p = q.ict
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(df)
    a = _atr(h, l, c)
    highs, lows = find_swings(df, p.swing_n)
    out: list[IctTrade] = []
    sim_p = FibParams(tps=q.tps, fractions=q.fractions, be_after=q.be_after, max_hold=p.max_hold)
    busy_until = -1

    for k in range(2, n - 1):
        bot, top = h[k - 1], l[k + 1]
        if top - bot < p.min_gap_atr * a[k]:
            continue
        made = k + 1
        if p.require_bos:
            prev = [s for s in highs if s.confirmed_at <= k - 1]
            if not prev:
                continue
            bos = [j for j in range(k - 1, min(n, k + 1 + p.bos_window)) if c[j] > prev[-1].price]
            if not bos:
                continue
            made = max(made, bos[0])
        below = [s.price for s in lows if s.confirmed_at <= made and s.price < bot]
        swing_anchor = below[-1] if below else float(l[max(0, k - 10) : k + 1].min())

        setup = None
        for t in range(made + 1, min(n, made + 1 + p.max_wait)):
            if setup is None:
                if t <= busy_until or c[t] < bot:
                    if c[t] < bot:
                        break
                    continue
                cand = [s for s in lows if s.idx > made and s.confirmed_at <= t - 1
                        and top < s.price <= top + p.liq_max_atr * a[made]]
                if not cand:
                    continue
                liq_s = cand[-1]
                if l[liq_s.idx + 1 : t].min(initial=np.inf) <= liq_s.price:
                    break                                  # płynność zebrana wcześniej, bez dotknięcia FVG
                if l[t] < liq_s.price and l[t] <= top:     # sweep płynności + dotknięcie FVG
                    f1 = float(h[liq_s.idx : t + 1].max())
                    setup = dict(touch=t, f0=l[t], f1=f1, liq=liq_s.price)
                continue
            # setup aktywny: zlecenie stop z poziomów z zamknięcia poprzedniej świecy
            f0, f1 = setup["f0"], setup["f1"]
            rng = f1 - f0
            stop = f0 + 0.1272 * rng
            sl = f0 - 0.1272 * rng if q.sl_mode == "fib" else min(f0, swing_anchor) - p.sl_buffer_atr * a[t - 1]
            risk = stop - sl
            if rng > 0 and risk >= p.min_risk and h[t] >= stop:
                entry = max(o[t], stop)
                levels = [x for x in (f0 + f * rng for f in q.tps) if x > entry]
                if levels:
                    if l[t] <= sl:
                        r, exits, closed = -1.0, [("sl", t, sl, 1.0)], True
                    else:
                        fr = q.fractions[-len(levels):]
                        r, exits, closed = _simulate(h, l, c, t, entry, sl, levels,
                                                     FibParams(**{**sim_p.__dict__, "fractions": fr}))
                    last_exit = exits[-1] if exits else ("open", n, entry, 0.0)
                    tr = IctTrade("BUY", k, setup["touch"], t, entry, sl, levels[-1], bot, top, setup["liq"],
                                  r=r, outcome=last_exit[0], exit_idx=last_exit[1], closed=closed,
                                  extra=dict(f0=f0, f1=f1))
                    out.append(tr)
                    busy_until = last_exit[1] if closed else n
                break
            if c[t] < bot or t - setup["touch"] > q.max_wait:
                break
            if l[t] < setup["f0"]:
                setup["f0"] = l[t]
    return out


def find_ictfib_trades(df: pd.DataFrame, q: IctFibParams | None = None) -> list[IctTrade]:
    q = q or IctFibParams()
    df = df.reset_index(drop=True)
    buys = _scan_buy_ictfib(df, q)
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    sells = _scan_buy_ictfib(m, q)
    for s in sells:
        s.direction = "SELL"
        s.entry, s.sl, s.tp = -s.entry, -s.sl, -s.tp
        s.fvg_bot, s.fvg_top = -s.fvg_top, -s.fvg_bot
        s.liq = -s.liq if s.liq is not None else None
    return sorted(buys + sells, key=lambda x: x.entry_idx)
