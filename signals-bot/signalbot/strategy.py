"""Detektor setupu: BOS/CHOCH -> retest strefy -> odrzucenie -> sygnał.

Logika SELL (BUY to lustrzane odbicie, liczone na zanegowanych cenach):

1. Świeca zamyka się poniżej ostatniego potwierdzonego swing low  -> BOS.
   Jeśli wcześniej struktura była wzrostowa (wyższe szczyty i dołki) -> CHOCH.
2. Strefa podaży = od przebitego poziomu do szczytu ruchu, który go przebił
   (ograniczona do `zone_max_atr` * ATR).
3. Impuls spadkowy robi dołek -> to będzie TP (wsparcie ze struktury).
4. Cena wraca do poziomu (retest). Szczyt retestu -> SL (+ bufor).
5. Świeca spadkowa zamyka się z powrotem poniżej poziomu -> wejście.
   Setup przepada, jeśli świeca zamknie się nad strefą albo minie `max_wait` świec.
6. Filtr: minimalny RR i minimalna wielkość impulsu.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .structure import atr, find_swings


@dataclass
class Params:
    swing_n: int = 3              # ile świec z każdej strony dla fraktala
    atr_period: int = 14
    zone_max_atr: float = 2.5     # maks. wysokość strefy w ATR
    max_wait: int = 48            # ile świec po BOS czekamy na retest (48 x M30 = 24h)
    min_impulse_atr: float = 2.0  # minimalny ruch od poziomu do dołka/szczytu impulsu
    sl_buffer_atr: float = 0.2    # bufor nad szczytem retestu
    min_rr: float = 1.5


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
    extreme_idx: int      # dołek (SELL) / szczyt (BUY) impulsu = TP
    retest_idx: int       # szczyt (SELL) / dołek (BUY) retestu = SL
    confirm_idx: int
    confirm_time: pd.Timestamp | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confirm_time"] = str(self.confirm_time) if self.confirm_time is not None else None
        return d


def _structure_type(lows: list, highs: list) -> str:
    """CHOCH jeśli przed przebiciem trend był przeciwny (HH + HL dla SELL)."""
    if len(lows) >= 2 and len(highs) >= 2:
        if lows[-1].price > lows[-2].price and highs[-1].price > highs[-2].price:
            return "CHOCH"
    return "BOS"


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
                    entry = c[t]
                    sl = active["retest_high"] + p.sl_buffer_atr * a[t]
                    tp = active["ext"]
                    risk, reward = sl - entry, entry - tp
                    impulse = active["level"] - active["ext"]
                    if (
                        risk > 0
                        and reward > 0
                        and impulse >= p.min_impulse_atr * active["atr"]
                        and reward / risk >= p.min_rr
                    ):
                        out.append(
                            dict(
                                break_type=active["type"],
                                level=active["level"],
                                zone_low=active["level"],
                                zone_high=active["zone_top"],
                                entry=entry,
                                sl=sl,
                                tp=tp,
                                rr=reward / risk,
                                atr=a[t],
                                swing_idx=active["swing_idx"],
                                break_idx=active["break_idx"],
                                extreme_idx=active["ext_idx"],
                                retest_idx=active["retest_idx"],
                                confirm_idx=t,
                            )
                        )
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
        leg_high = float(h[s.idx : t + 1].max())
        active = dict(
            type=_structure_type(known_lows, known_highs),
            level=s.price,
            zone_top=min(leg_high, s.price + p.zone_max_atr * a[t]),
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


def _mirror(df: pd.DataFrame) -> pd.DataFrame:
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    return m


def find_setups(df: pd.DataFrame, p: Params | None = None) -> list[Setup]:
    """Wszystkie setupy w historii (posortowane po świecy potwierdzenia)."""
    p = p or Params()
    df = df.reset_index(drop=True) if "time" in df.columns else df
    times = df["time"] if "time" in df.columns else None
    setups: list[Setup] = []

    for raw in _scan_sell(df, p):
        setups.append(Setup(direction="SELL", **raw))
    for raw in _scan_sell(_mirror(df), p):
        flip = {k: -raw[k] for k in ("level", "entry", "sl", "tp")}
        setups.append(
            Setup(
                direction="BUY",
                break_type=raw["break_type"],
                zone_low=-raw["zone_high"],
                zone_high=-raw["zone_low"],
                rr=raw["rr"],
                atr=raw["atr"],
                swing_idx=raw["swing_idx"],
                break_idx=raw["break_idx"],
                extreme_idx=raw["extreme_idx"],
                retest_idx=raw["retest_idx"],
                confirm_idx=raw["confirm_idx"],
                **flip,
            )
        )
    for s in setups:
        for k in ("level", "zone_low", "zone_high", "entry", "sl", "tp", "rr", "atr"):
            setattr(s, k, float(getattr(s, k)))
        if times is not None:
            s.confirm_time = pd.Timestamp(times.iloc[s.confirm_idx])
    setups.sort(key=lambda s: s.confirm_idx)
    return setups
