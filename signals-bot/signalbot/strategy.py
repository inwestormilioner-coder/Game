"""Detektor setupu: BOS/CHOCH -> retest strefy -> odrzucenie -> sygnał.

Logika SELL (BUY to lustrzane odbicie, liczone na zanegowanych cenach):

1. Świeca zamyka się poniżej ostatniego potwierdzonego swing low  -> BOS.
   Jeśli wcześniej struktura była wzrostowa (wyższe szczyty i dołki) -> CHOCH.
2. Strefa podaży = od przebitego poziomu do szczytu ruchu, który go przebił
   (ograniczona do `zone_max_atr` * ATR).
3. Impuls spadkowy robi dołek -> TP (wsparcie ze struktury).
4. Cena wraca do poziomu (retest). Szczyt retestu -> SL (+ bufor).
5. Świeca spadkowa zamyka się z powrotem poniżej poziomu -> wejście.
   Setup przepada, jeśli świeca zamknie się nad strefą albo minie `max_wait` świec.
6. Filtr: minimalny RR i minimalna wielkość impulsu.

Konfluencje (liczone zawsze, filtrowane opcjonalnie przez `require` / `min_score`):
- fibo:  retest sięgnął 50–78,6% impulsu (strefa premium / OTE),
- fvg:   retest wszedł w lukę (Fair Value Gap) zostawioną przez impuls,
- sweep: retest wybił wcześniejszy swing high (zebrał płynność BSL) i wrócił pod poziom.
Cel płynnościowy (SSL): najbliższy starszy swing low poniżej dołka impulsu
— używany jako TP, gdy `tp_mode="liquidity"`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .structure import atr, find_swings

FACTORS = ("fibo", "fvg", "sweep")


@dataclass
class Params:
    swing_n: int = 3              # ile świec z każdej strony dla fraktala
    atr_period: int = 14
    zone_max_atr: float = 2.5     # maks. wysokość strefy w ATR
    max_wait: int = 48            # ile świec po BOS czekamy na retest (48 x M30 = 24h)
    min_impulse_atr: float = 2.0  # minimalny ruch od poziomu do dołka/szczytu impulsu
    sl_buffer_atr: float = 0.2    # bufor nad szczytem retestu
    min_rr: float = 1.5
    fibo_min: float = 0.5
    fibo_max: float = 0.786
    tp_mode: str = "impulse"      # impulse | liquidity
    require: tuple[str, ...] = ()  # konfluencje wymagane, np. ("fibo",)
    min_score: int = 0            # minimalna liczba konfluencji


@dataclass
class Setup:
    direction: str        # SELL / BUY
    break_type: str       # BOS / CHOCH
    level: float          # przebity poziom (krawędź strefy)
    zone_low: float
    zone_high: float
    entry: float
    sl: float
    tp: float
    rr: float
    atr: float
    swing_idx: int        # świeca, na której był przebity swing
    break_idx: int
    extreme_idx: int      # dołek (SELL) / szczyt (BUY) impulsu
    retest_idx: int       # szczyt (SELL) / dołek (BUY) retestu = SL
    confirm_idx: int
    # konfluencje
    leg_start: float = 0.0    # początek impulsu (0% fibo)
    leg_end: float = 0.0      # koniec impulsu (100% fibo)
    retrace: float = 0.0      # jak głęboko sięgnął retest (0-1)
    fibo: bool = False
    fvg: bool = False
    fvg_low: float | None = None
    fvg_high: float | None = None
    sweep: bool = False
    sweep_price: float | None = None
    liq_target: float | None = None
    score: int = 0
    confirm_time: pd.Timestamp | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confirm_time"] = str(self.confirm_time) if self.confirm_time is not None else None
        return d


PRICE_KEYS = ("level", "entry", "sl", "tp", "leg_start", "leg_end", "sweep_price", "liq_target")
PAIR_KEYS = (("zone_low", "zone_high"), ("fvg_low", "fvg_high"))


def _structure_type(lows: list, highs: list) -> str:
    """CHOCH jeśli przed przebiciem trend był przeciwny (HH + HL dla SELL)."""
    if len(lows) >= 2 and len(highs) >= 2:
        if lows[-1].price > lows[-2].price and highs[-1].price > highs[-2].price:
            return "CHOCH"
    return "BOS"


def _bearish_fvgs(h: np.ndarray, l: np.ndarray, start: int, end: int) -> list[tuple[float, float]]:
    """Luki spadkowe: low świecy k-1 powyżej high świecy k+1 (k w impulsie)."""
    gaps = []
    for k in range(max(start, 1), min(end, len(h) - 1)):
        if l[k - 1] > h[k + 1]:
            gaps.append((float(h[k + 1]), float(l[k - 1])))
    return gaps


def _scan_sell(df: pd.DataFrame, p: Params) -> list[dict]:
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    a = atr(df, p.atr_period).to_numpy()
    swing_highs, swing_lows = find_swings(df, p.swing_n)

    out: list[dict] = []
    used: set[int] = set()
    active: dict | None = None
    start = max(p.atr_period, 2 * p.swing_n + 1)

    for t in range(start, len(df)):
        # --- obsługa aktywnego setupu ---
        if active is not None and t > active["break_idx"]:
            if t - active["break_idx"] > p.max_wait or c[t] > active["zone_top"]:
                active = None
            else:
                if not active["touched"] and l[t] < active["ext"]:
                    active["ext"], active["ext_idx"] = l[t], t
                if h[t] >= active["level"]:
                    active["touched"] = True
                    if h[t] > active["retest_high"]:
                        active["retest_high"], active["retest_idx"] = h[t], t
                if active["touched"] and c[t] < active["level"] and c[t] < o[t]:
                    raw = _build(active, t, c, h, l, a, swing_highs, swing_lows, p)
                    if raw is not None:
                        out.append(raw)
                    active = None
                    continue

        # --- nowe przebicie struktury ---
        known_lows = [s for s in swing_lows if s.confirmed_at <= t - 1]
        if not known_lows:
            continue
        s = known_lows[-1]
        if s.idx in used or c[t] >= s.price:
            continue
        used.add(s.idx)
        if active is not None and active["touched"]:
            continue  # trwa retest wcześniejszego poziomu
        known_highs = [x for x in swing_highs if x.confirmed_at <= t - 1]
        leg_idx = s.idx + int(np.argmax(h[s.idx : t + 1]))
        leg_high = float(h[leg_idx])
        active = dict(
            type=_structure_type(known_lows, known_highs),
            level=s.price,
            zone_top=min(leg_high, s.price + p.zone_max_atr * a[t]),
            leg_high=leg_high,
            leg_idx=leg_idx,
            swing_idx=s.idx,
            break_idx=t,
            ext=l[t],
            ext_idx=t,
            touched=False,
            retest_high=-np.inf,
            retest_idx=None,
            atr=a[t],
        )
    return out


def _build(st: dict, t: int, c, h, l, a, swing_highs, swing_lows, p: Params) -> dict | None:
    entry = c[t]
    sl = st["retest_high"] + p.sl_buffer_atr * a[t]
    impulse = st["level"] - st["ext"]
    if impulse < p.min_impulse_atr * st["atr"]:
        return None

    # fibo: głębokość retestu względem impulsu leg_high -> ext
    rng = st["leg_high"] - st["ext"]
    retrace = (st["retest_high"] - st["ext"]) / rng if rng > 0 else 0.0
    fibo = p.fibo_min <= retrace <= p.fibo_max

    # FVG zostawione przez impuls i dotknięte przez retest
    gaps = [g for g in _bearish_fvgs(h, l, st["leg_idx"] + 1, st["ext_idx"])
            if st["retest_high"] >= g[0]]
    fvg = gaps[-1] if gaps else None

    # sweep: retest wybił wcześniejszy swing high ponad poziomem (płynność BSL)
    swept = [x.price for x in swing_highs
             if x.confirmed_at <= st["retest_idx"] and x.idx < st["break_idx"]
             and x.idx >= st["swing_idx"] - 50 and st["level"] < x.price <= st["retest_high"]]
    sweep_price = max(swept) if swept else None

    # cel płynnościowy: najbliższy starszy swing low poniżej dołka impulsu
    lower = [x.price for x in swing_lows
             if x.confirmed_at <= t and x.idx < st["swing_idx"] and x.price < st["ext"]]
    liq_target = max(lower) if lower else None

    tp = liq_target if (p.tp_mode == "liquidity" and liq_target is not None) else st["ext"]
    risk, reward = sl - entry, entry - tp
    if risk <= 0 or reward <= 0 or reward / risk < p.min_rr:
        return None

    flags = {"fibo": fibo, "fvg": fvg is not None, "sweep": sweep_price is not None}
    score = sum(flags.values())
    if any(not flags[f] for f in p.require) or score < p.min_score:
        return None

    return dict(
        break_type=st["type"], level=st["level"], zone_low=st["level"], zone_high=st["zone_top"],
        entry=entry, sl=sl, tp=tp, rr=reward / risk, atr=a[t],
        swing_idx=st["swing_idx"], break_idx=st["break_idx"], extreme_idx=st["ext_idx"],
        retest_idx=st["retest_idx"], confirm_idx=t,
        leg_start=st["leg_high"], leg_end=st["ext"], retrace=retrace,
        fibo=fibo, fvg=fvg is not None,
        fvg_low=fvg[0] if fvg else None, fvg_high=fvg[1] if fvg else None,
        sweep=sweep_price is not None, sweep_price=sweep_price,
        liq_target=liq_target, score=score,
    )


def _mirror(df: pd.DataFrame) -> pd.DataFrame:
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    return m


def _unmirror(raw: dict) -> dict:
    out = dict(raw)
    for k in PRICE_KEYS:
        if out[k] is not None:
            out[k] = -out[k]
    for lo, hi in PAIR_KEYS:
        if raw[lo] is not None:
            out[lo], out[hi] = -raw[hi], -raw[lo]
    return out


def find_setups(df: pd.DataFrame, p: Params | None = None) -> list[Setup]:
    """Wszystkie setupy w historii (posortowane po świecy potwierdzenia)."""
    p = p or Params()
    df = df.reset_index(drop=True)
    times = df["time"] if "time" in df.columns else None
    setups = [Setup(direction="SELL", **raw) for raw in _scan_sell(df, p)]
    setups += [Setup(direction="BUY", **_unmirror(raw)) for raw in _scan_sell(_mirror(df), p)]
    for s in setups:
        for k in ("zone_low", "zone_high", "rr", "atr", "retrace", *PRICE_KEYS, "fvg_low", "fvg_high"):
            v = getattr(s, k)
            if v is not None:
                setattr(s, k, float(v))
        s.fibo, s.fvg, s.sweep = bool(s.fibo), bool(s.fvg), bool(s.sweep)
        if times is not None:
            s.confirm_time = pd.Timestamp(times.iloc[s.confirm_idx])
    setups.sort(key=lambda s: s.confirm_idx)
    return setups
