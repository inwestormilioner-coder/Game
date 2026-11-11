"""Formacje cenowe: double / triple top i bottom, głowa z ramionami (i odwrócona) oraz harmoniczne XABCD
(Gartley, Bat, Alt Bat, Butterfly, Crab, Deep Crab, Cypher, Shark).

Wszystko liczone przyczynowo (bez zaglądania w przyszłość), świeca po świecy:

1. Pivoty z ZigZaga ATR: szczyt/dołek jest potwierdzony, gdy cena cofnie się od niego o `depth` x ATR.
   Bieżące, jeszcze niepotwierdzone ekstremum nogi jest „prowizorycznym” pivotem (np. punkt D w trakcie).
2. Formacje klasyczne potwierdza zamknięcie świecy za neckline. Wejście = zamknięcie tej świecy,
   SL za szczytami / dołkami formacji, TP = zasięg formacji x 1.0 i x 1.618 (rozszerzenie Fibo).
3. Harmoniczne: X, A, B, C to potwierdzone pivoty, D to bieżące ekstremum nogi C-D. Sygnał, gdy D leży
   w PRZ (strefa z proporcji Fibo) i świeca odrzuca PRZ (zamknięcie w kierunku sygnału, knot od D).
   SL za dalszą krawędzią PRZ, TP 0.382 i 0.618 ruchu A-D.
4. Konfluencje (scoring): strefy order block jak we wskaźniku TPZ (M15 i H1), Wasze strefy z pliku,
   poziom Fibo większego ruchu, Volume Profile i struktura H1.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .structure import find_swings, volume_profile

CHART_KINDS = ("double_top", "double_bottom", "triple_top", "triple_bottom", "head_shoulders",
               "inv_head_shoulders", "rising_wedge", "falling_wedge")
HARMONIC_KINDS = ("gartley", "bat", "alt_bat", "butterfly", "crab", "deep_crab", "cypher", "shark")
ALL_KINDS = CHART_KINDS + HARMONIC_KINDS

NAMES = {
    "double_top": "Double Top", "double_bottom": "Double Bottom", "triple_top": "Triple Top",
    "triple_bottom": "Triple Bottom", "head_shoulders": "Head & Shoulders",
    "inv_head_shoulders": "Inverse Head & Shoulders", "rising_wedge": "Rising Wedge",
    "falling_wedge": "Falling Wedge", "gartley": "Gartley", "bat": "Bat",
    "alt_bat": "Alternate Bat", "butterfly": "Butterfly", "crab": "Crab", "deep_crab": "Deep Crab",
    "cypher": "Cypher", "shark": "Shark",
}

# Proporcje harmonicznych: b = AB/XA, c = BC/AB, d = AD/XA (albo CD/XC dla Cypher/Shark), cd = CD/BC.
# Każdy zakres to (min, max); "d_ref" = poziom idealny (do PRZ i opisu).
HARMONICS: dict[str, dict] = {
    "gartley":   dict(b=(0.568, 0.668), c=(0.382, 0.886), d=(0.75, 0.82), d_ref=0.786, cd=(1.13, 1.618), d_of="XA"),
    "bat":       dict(b=(0.382, 0.50), c=(0.382, 0.886), d=(0.85, 0.92), d_ref=0.886, cd=(1.618, 2.618), d_of="XA"),
    "alt_bat":   dict(b=(0.30, 0.382), c=(0.382, 0.886), d=(1.10, 1.16), d_ref=1.13, cd=(2.0, 3.618), d_of="XA"),
    "butterfly": dict(b=(0.75, 0.82), c=(0.382, 0.886), d=(1.27, 1.618), d_ref=1.272, cd=(1.618, 2.618), d_of="XA"),
    "crab":      dict(b=(0.382, 0.618), c=(0.382, 0.886), d=(1.58, 1.66), d_ref=1.618, cd=(2.24, 3.618), d_of="XA"),
    "deep_crab": dict(b=(0.85, 0.92), c=(0.382, 0.886), d=(1.58, 1.66), d_ref=1.618, cd=(2.0, 3.618), d_of="XA"),
    "cypher":    dict(b=(0.382, 0.618), c=(1.13, 1.414), d=(0.75, 0.82), d_ref=0.786, cd=None, d_of="XC"),
    "shark":     dict(b=(0.382, 0.886), c=(1.13, 1.618), d=(0.86, 1.16), d_ref=0.886, cd=(1.618, 2.24), d_of="XC"),
}
BC_EXT = (1.13, 1.272, 1.414, 1.618, 2.0, 2.24, 2.618, 3.14, 3.618)   # rozszerzenia BC do klastra PRZ
KEY_RETR = (0.5, 0.618, 0.705, 0.786, 0.886)
KEY_EXT = (1.272, 1.414, 1.618)


@dataclass
class PatternParams:
    depths: tuple[float, ...] = (2.0, 4.0)   # ZigZag: odwrócenie o tyle ATR potwierdza pivot (kilka skal)
    kinds: tuple[str, ...] = ALL_KINDS
    eq_tol_atr: float = 0.6                  # szczyty double/triple top: różnica max tyle ATR...
    eq_tol_height: float = 0.15              # ...albo tyle wysokości formacji (większa z dwóch)
    min_height_atr: float = 1.5              # minimalna wysokość formacji (szczyt - neckline) w ATR
    min_sep: int = 5                         # min. świec między szczytami / dołkami
    max_break_wait: int = 40                 # ile świec po ostatnim szczycie czekamy na przebicie neckline
    max_chase: float = 0.35                  # wejście nie dalej niż tyle wysokości za neckline
    sl_buf_atr: float = 0.25                 # bufor SL za formacją / PRZ
    chart_tps: tuple[float, ...] = (1.0, 1.618)   # cele formacji klasycznych: x wysokość od neckline
    wedge_tps: tuple[float, ...] = (0.618, 1.0)   # kliny: x szerokość klina u podstawy, od punktu wybicia
    wedge_fit_atr: float = 0.5               # klin: max odchyłka szczytów / dołków od linii (ATR)
    wedge_min_bars: int = 15                 # klin: min. długość
    wedge_squeeze: float = 0.75              # klin: szerokość na końcu < tyle x szerokość na początku
    harm_tps: tuple[float, ...] = (0.382, 0.618)  # cele harmonicznych: retracement ruchu A-D od D
    ratio_slack: float = 0.03                # tolerancja proporcji harmonicznych (względna)
    rej_atr: float = 0.3                     # harmoniczne: minimalne odbicie zamknięcia od D (ATR)
    min_rr: float = 1.2                      # RR liczone do ostatniego celu
    max_hold: int = 96
    zone_swing_n: int = 3                    # strefy order block jak w strategii fibzone / TPZ
    vp_lookback: int = 200


@dataclass
class Pattern:
    kind: str
    direction: str                           # BUY | SELL
    points: list                             # [(idx, cena, etykieta), ...]
    confirm_idx: int
    entry: float
    sl: float
    tps: list
    depth: float
    neckline: list | None = None             # [(idx1, cena1), (idx2, cena2)]
    prz: list | None = None                  # [dół, góra]
    ratios: dict = field(default_factory=dict)
    confluences: list = field(default_factory=list)   # opisy konfluencji (po angielsku, do posta)
    score: int = 0
    details: dict = field(default_factory=dict)
    confirm_time: str = ""
    # wynik (backtest / śledzenie)
    outcome: str = "open"
    r: float = 0.0
    exits: list = field(default_factory=list)

    @property
    def family(self) -> str:
        return "harmonic" if self.kind in HARMONIC_KINDS else "chart"

    @property
    def name(self) -> str:
        bull = "Bullish " if self.direction == "BUY" else "Bearish "
        return (bull if self.family == "harmonic" else "") + NAMES[self.kind]

    @property
    def key(self) -> str:
        """Ta sama formacja z dwóch skal ZigZaga ma ten sam klucz (po punktach formacji)."""
        return f"{self.kind}-{self.points[-1][0]}-{self.points[0][0]}"

    @property
    def id(self) -> str:
        t = pd.Timestamp(self.confirm_time).strftime("%Y%m%d%H%M") if self.confirm_time else str(self.confirm_idx)
        return f"PAT-{self.kind}-{self.direction}-{t}"

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def rr(self) -> float:
        return abs(self.tps[-1] - self.entry) / self.risk if self.risk else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"], d["name"] = self.id, self.name
        return d


# ----------------------------------------------------------------------------- pivoty

@dataclass(frozen=True)
class Pivot:
    idx: int
    price: float
    kind: str            # H | L
    confirmed_at: int    # -1 = prowizoryczny (bieżące ekstremum nogi)


def atr_array(h, l, c, n: int = 14) -> np.ndarray:
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def zigzag(h: np.ndarray, l: np.ndarray, a: np.ndarray, depth: float):
    """ZigZag ATR. Zwraca (potwierdzone pivoty, leg[t], ext[t]):
    leg[t] = 1 gdy po świecy t trwa noga wzrostowa (śledzimy szczyt), -1 spadkowa, 0 jeszcze brak;
    ext[t] = indeks bieżącego ekstremum nogi po świecy t."""
    n = len(h)
    pivots: list[Pivot] = []
    leg = np.zeros(n, dtype=int)
    ext = np.zeros(n, dtype=int)
    d, hi_i, lo_i, e = 0, 0, 0, 0
    for t in range(1, n):
        thr = depth * a[t]
        if d == 0:
            if h[t] > h[hi_i]:
                hi_i = t
            if l[t] < l[lo_i]:
                lo_i = t
            if h[hi_i] - l[lo_i] >= thr:
                if hi_i > lo_i:
                    pivots.append(Pivot(lo_i, float(l[lo_i]), "L", t))
                    d, e = 1, hi_i
                else:
                    pivots.append(Pivot(hi_i, float(h[hi_i]), "H", t))
                    d, e = -1, lo_i
        elif d == 1:
            if h[t] >= h[e]:
                e = t
            elif h[e] - l[t] >= thr:
                pivots.append(Pivot(e, float(h[e]), "H", t))
                d, e = -1, e + 1 + int(np.argmin(l[e + 1 : t + 1]))
        else:
            if l[t] <= l[e]:
                e = t
            elif h[t] - l[e] >= thr:
                pivots.append(Pivot(e, float(l[e]), "L", t))
                d, e = 1, e + 1 + int(np.argmax(h[e + 1 : t + 1]))
        leg[t], ext[t] = d, e
    return pivots, leg, ext


def _sequence(pivots: list[Pivot], k: int, t: int, leg: np.ndarray, ext: np.ndarray,
              h: np.ndarray, l: np.ndarray, tail: int = 7) -> list[Pivot]:
    """Ostatnie pivoty znane po świecy t: `k` potwierdzonych + prowizoryczne ekstremum bieżącej nogi."""
    seq = list(pivots[max(0, k - tail) : k])
    if leg[t] == 1:
        seq.append(Pivot(int(ext[t]), float(h[ext[t]]), "H", -1))
    elif leg[t] == -1:
        seq.append(Pivot(int(ext[t]), float(l[ext[t]]), "L", -1))
    return seq


# ----------------------------------------------------------------------------- formacje klasyczne

def _tops_tail(seq: list[Pivot], kind: str) -> list[Pivot] | None:
    """Ogon sekwencji kończący się ostatnim pivotem rodzaju `kind` (szczyt dla tops)."""
    j = next((i for i in range(len(seq) - 1, -1, -1) if seq[i].kind == kind), None)
    return seq[: j + 1] if j is not None else None


def _chart_candidates(seq: list[Pivot], a_t: float, p: PatternParams) -> list[dict]:
    """Kandydaci na double/triple top i H&S. Dołki (double bottom itd.) liczymy tym samym kodem na lustrze cen."""
    tail = _tops_tail(seq, "H")
    out = []
    if not tail or len(tail) < 4:
        return out
    tol = lambda height: max(p.eq_tol_atr * a_t, p.eq_tol_height * height)  # noqa: E731
    # double: [pre L] H1 L H2
    pre, h1, lo, h2 = tail[-4:]
    if pre.kind == "L" and h1.kind == "H" and lo.kind == "L" and h2.idx - h1.idx >= p.min_sep:
        height = min(h1.price, h2.price) - lo.price
        if height >= p.min_height_atr * a_t and abs(h1.price - h2.price) <= tol(height) and pre.price < lo.price:
            out.append(dict(kind="double_top", pts=[h1, lo, h2],
                            labels=["Top 1", "", "Top 2"],
                            neck=[(lo.idx, lo.price), (h2.idx, lo.price)], height=height,
                            extreme=max(h1.price, h2.price), last=h2))
    if len(tail) >= 6:
        pre, h1, l1, h2, l2, h3 = tail[-6:]
        if pre.kind == "L" and all(x.kind == "H" for x in (h1, h2, h3)) and \
                h2.idx - h1.idx >= p.min_sep and h3.idx - h2.idx >= p.min_sep:
            hs = [h1.price, h2.price, h3.price]
            neck_lo = min(l1.price, l2.price)
            # triple: trzy szczyty na jednym poziomie, neckline = niższy z dołków
            height = min(hs) - neck_lo
            if height >= p.min_height_atr * a_t and max(hs) - min(hs) <= tol(height) and pre.price < neck_lo:
                out.append(dict(kind="triple_top", pts=[h1, l1, h2, l2, h3],
                                labels=["Top 1", "", "Top 2", "", "Top 3"],
                                neck=[(l1.idx, neck_lo), (h3.idx, neck_lo)], height=height, extreme=max(hs),
                                last=h3))
            # H&S: głowa wyżej niż oba ramiona, ramiona podobne, neckline przez oba dołki (może być pochyła)
            head_h = h2.price - max(l1.price, l2.price)
            if head_h >= p.min_height_atr * a_t and h2.price - max(h1.price, h3.price) >= tol(head_h) and \
                    abs(h1.price - h3.price) <= max(p.eq_tol_atr * a_t, 0.3 * head_h) and pre.price < min(l1.price, l2.price):
                slope = (l2.price - l1.price) / (l2.idx - l1.idx)
                out.append(dict(kind="head_shoulders", pts=[h1, l1, h2, l2, h3],
                                labels=["L Shoulder", "", "Head", "", "R Shoulder"],
                                neck=[(l1.idx, l1.price), (l2.idx, l2.price)], slope=slope,
                                height=h2.price - (l1.price + slope * (h2.idx - l1.idx)),
                                extreme=h3.price, last=h3))
    return out


def _line(pts: list) -> tuple[float, float]:
    """Prosta (nachylenie, wyraz wolny) dopasowana do pivotów metodą najmniejszych kwadratów."""
    x = np.array([q.idx for q in pts], dtype=float)
    y = np.array([q.price for q in pts], dtype=float)
    if len(pts) == 2:
        m = (y[1] - y[0]) / (x[1] - x[0])
        return m, y[0] - m * x[0]
    m, b = np.polyfit(x, y, 1)
    return float(m), float(b)


def _wedge_candidates(seq: list[Pivot], a_t: float, p: PatternParams) -> list[dict]:
    """Klin rosnący (Rising Wedge, SELL): coraz wyższe szczyty i dołki, linie zbiegają się (dołki rosną
    szybciej niż szczyty). Klin spadający (BUY) liczymy tym samym kodem na lustrze cen.
    Sygnał: zamknięcie pod dolną linią. Kontekst: odwrócenie po wzroście albo kontynuacja spadku."""
    tail = _tops_tail(seq, "H")
    out = []
    if not tail or len(tail) < 5:
        return out
    for size in (6, 5):                      # L H L H L H (3+3) albo H L H L H (3 szczyty, 2 dołki)
        if len(tail) < size:
            continue
        pts = tail[-size:]
        hs = [q for q in pts if q.kind == "H"]
        ls = [q for q in pts if q.kind == "L"]
        if len(hs) < 2 or len(ls) < 2:
            continue
        if not all(b.price > a.price for a, b in zip(hs, hs[1:])) or \
                not all(b.price > a.price for a, b in zip(ls, ls[1:])):
            continue
        legs = [abs(b.price - a.price) for a, b in zip(pts, pts[1:])]
        gaps = [b.idx - a.idx for a, b in zip(pts, pts[1:])]
        if max(legs) > 3 * min(legs) or max(gaps) > 3 * min(gaps):
            continue                         # klin = podobne odbicia między liniami, nie jeden wielki ruch
        mu, bu = _line(hs)
        ml, bl = _line(ls)
        if not (ml > mu > 0):                # obie rosną, dolna szybciej = zbieżne
            continue
        fit = max([abs(q.price - (mu * q.idx + bu)) for q in hs] + [abs(q.price - (ml * q.idx + bl)) for q in ls])
        if fit > p.wedge_fit_atr * a_t:
            continue
        i0, i1 = pts[0].idx, pts[-1].idx
        if i1 - i0 < p.wedge_min_bars:
            continue
        w0 = (mu - ml) * i0 + bu - bl
        w1 = (mu - ml) * i1 + bu - bl
        if w0 < p.min_height_atr * a_t or w1 <= 0 or w1 > p.wedge_squeeze * w0:
            continue
        apex = (bl - bu) / (mu - ml)
        labels = ["HH" if q.kind == "H" else "HL" for q in pts]
        out.append(dict(kind="rising_wedge", pts=pts, labels=labels, neck=[(i0, ml * i0 + bl), (i1, ml * i1 + bl)],
                        slope=ml, upper=(mu, bu), height=w0, extreme=hs[-1].price, last=hs[-1], apex=apex))
        break
    return out


def _neck_at(c: dict, i: int) -> float:
    (i1, p1), _ = c["neck"]
    return p1 + c.get("slope", 0.0) * (i - i1)


# ----------------------------------------------------------------------------- harmoniczne

def _in(x: float, rng: tuple, slack: float) -> bool:
    return rng[0] * (1 - slack) <= x <= rng[1] * (1 + slack)


def harmonic_ratios(X: float, A: float, B: float, C: float, D: float) -> dict:
    xa, ab, bc, cd = abs(A - X), abs(A - B), abs(C - B), abs(C - D)
    xc = abs(C - X)
    return dict(b=ab / xa if xa else 0, c=bc / ab if ab else 0, d_xa=abs(A - D) / xa if xa else 0,
                d_xc=cd / xc if xc else 0, cd=cd / bc if bc else 0)


def match_harmonic(X, A, B, C, D, slack: float = 0.03, kinds=HARMONIC_KINDS) -> list[str]:
    """Nazwy harmonicznych pasujących do punktów (bycze: X dołek, A szczyt, ... D dołek; niedźwiedzie
    lustrzanie). Sprawdza też kierunek nóg."""
    bull = A > X
    s = 1 if bull else -1
    if not (s * (A - X) > 0 and s * (A - B) > 0 and s * (C - B) > 0 and s * (C - D) > 0):
        return []
    r = harmonic_ratios(X, A, B, C, D)
    out = []
    for k in kinds:
        if k not in HARMONICS:
            continue
        g = HARMONICS[k]
        d = r["d_xa"] if g["d_of"] == "XA" else r["d_xc"]
        if _in(r["b"], g["b"], slack) and _in(r["c"], g["c"], slack) and _in(d, g["d"], slack) and \
                (g["cd"] is None or _in(r["cd"], g["cd"], slack)):
            out.append(k)
    return out


def harmonic_prz(kind: str, X, A, B, C) -> tuple[float, float]:
    """PRZ = przedział cen D wynikający z proporcji D (XA albo XC)."""
    g = HARMONICS[kind]
    s = 1 if A > X else -1
    if g["d_of"] == "XA":
        p1, p2 = A - s * g["d"][0] * abs(A - X), A - s * g["d"][1] * abs(A - X)
    else:
        p1, p2 = C - s * g["d"][0] * abs(C - X), C - s * g["d"][1] * abs(C - X)
    return min(p1, p2), max(p1, p2)


def fib_cluster(kind: str, X, A, B, C, D, a_t: float) -> list[str]:
    """Które projekcje Fibo trafiają w D (w granicach 0.5 ATR): proporcja D, rozszerzenie BC, AB=CD."""
    g = HARMONICS[kind]
    s = 1 if A > X else -1
    hits = []
    ref = (A - s * g["d_ref"] * abs(A - X)) if g["d_of"] == "XA" else (C - s * g["d_ref"] * abs(C - X))
    if abs(ref - D) <= 0.5 * a_t:
        hits.append(f"{g['d_ref']:g} {g['d_of']}")
    for e in BC_EXT:
        if abs((C - s * e * abs(C - B)) - D) <= 0.5 * a_t:
            hits.append(f"{e:g} BC")
            break
    if abs((C - s * abs(A - B)) - D) <= 0.5 * a_t:
        hits.append("AB=CD")
    return hits


# ----------------------------------------------------------------------------- strefy i konfluencje

@dataclass
class Zone:
    bot: float
    top: float
    side: str            # demand | supply
    created: int         # znana od świecy (włącznie)
    dead: int | None     # unieważniona na tej świecy
    source: str = "M"    # M (interwał bota) | H1 | user
    label: str = ""

    def active(self, t: int) -> bool:
        return self.created <= t and (self.dead is None or self.dead > t)


def _demand_zones(df: pd.DataFrame, swing_n: int) -> list[list]:
    """Order blocki jak w strategii fibzone / wskaźniku TPZ: świeca z najniższym dołkiem między swing high
    a świecą, która go przebiła. Unieważnienie: zamknięcie pod strefą."""
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    highs, _ = find_swings(df, swing_n)
    zones, used, live, j = [], set(), [], 0
    for t in range(1, len(df)):
        while j < len(highs) and highs[j].confirmed_at <= t - 1:
            j += 1
        sh = highs[j - 1] if j else None
        if sh is not None and sh.idx not in used and c[t] > sh.price:
            used.add(sh.idx)
            ob = sh.idx + int(np.argmin(l[sh.idx : t + 1]))
            z = [float(l[ob]), float(h[ob]), t, None]
            zones.append(z)
            live.append(z)
        for z in list(live):
            if t > z[2] and c[t] < z[0]:
                z[3] = t
                live.remove(z)
    return zones


def _mirror(df: pd.DataFrame) -> pd.DataFrame:
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    return m


def order_block_zones(df: pd.DataFrame, swing_n: int = 3, source: str = "M") -> list[Zone]:
    out = [Zone(b, t, "demand", c, d, source) for b, t, c, d in _demand_zones(df, swing_n)]
    out += [Zone(-t, -b, "supply", c, d, source) for b, t, c, d in _demand_zones(_mirror(df), swing_n)]
    return out


def h1_frame(df: pd.DataFrame) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    return df.set_index(pd.DatetimeIndex(df["time"])).resample("1h", label="left", closed="left").agg(agg) \
        .dropna().reset_index().rename(columns={"index": "time"})


def h1_zones(df: pd.DataFrame, swing_n: int = 2) -> list[Zone]:
    """Strefy H1 przeliczone na indeksy świec bota: znane od świecy, na której zamknęła się świeca H1."""
    if len(df) < 2:
        return []
    h1 = h1_frame(df)
    step = df["time"].iloc[1] - df["time"].iloc[0]
    bar_close = (df["time"] + step).to_numpy()
    h1_close = (h1["time"] + pd.Timedelta(hours=1)).to_numpy()

    def to_bar(k: int | None) -> int | None:
        if k is None:
            return None
        return int(np.searchsorted(bar_close, h1_close[k], side="left"))

    out = []
    for z in order_block_zones(h1, swing_n, "H1"):
        out.append(Zone(z.bot, z.top, z.side, to_bar(z.created), to_bar(z.dead), "H1"))
    return out


def load_user_zones(path: str | Path | None) -> list[Zone]:
    """Wasze strefy z pliku JSON: [{"bot": 4100, "top": 4110, "side": "supply", "label": "D1 supply"}, ...].
    "side" może być pominięte (strefa działa wtedy w obie strony)."""
    if not path or not Path(path).exists():
        return []
    out = []
    for z in json.loads(Path(path).read_text(encoding="utf-8")):
        lo, hi = sorted((float(z["bot"]), float(z["top"])))
        out.append(Zone(lo, hi, z.get("side", "any"), 0, None, "user", z.get("label", "")))
    return out


def _h1_structure(df: pd.DataFrame, t: int) -> str:
    """Struktura H1 z zamkniętych świec H1 do świecy t: bullish / bearish / ranging / unclear."""
    d = df.iloc[: t + 1]
    if len(d) < 2:
        return "unclear"
    h1 = h1_frame(d)
    step = d["time"].iloc[1] - d["time"].iloc[0]
    h1 = h1[h1["time"] + pd.Timedelta(hours=1) <= d["time"].iloc[-1] + step].reset_index(drop=True)
    if len(h1) < 20:
        return "unclear"
    highs, lows = find_swings(h1, 2)
    end = len(h1) - 1
    hs = [s.price for s in highs if s.confirmed_at <= end][-2:]
    ls = [s.price for s in lows if s.confirmed_at <= end][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return "unclear"
    if hs[1] > hs[0] and ls[1] > ls[0]:
        return "bullish"
    if hs[1] < hs[0] and ls[1] < ls[0]:
        return "bearish"
    return "ranging"


def _major_fib(h, l, start: int, price: float, sell: bool, a_t: float, lookback: int = 200) -> str | None:
    """Czy cena (szczyt / D) leży na kluczowym poziomie Fibo większego ruchu przed formacją.
    SELL: ruch spadkowy od najwyższego szczytu z `lookback` świec do dołka po nim - retracement 0.5-0.886,
    albo rozszerzenie 1.272-1.618, gdy cena przebiła ten szczyt."""
    s = max(0, start - lookback)
    if start - s < 10:
        return None
    if sell:
        i_hi = s + int(np.argmax(h[s:start]))
        if i_hi + 1 >= start:
            return None
        lo = float(l[i_hi:start].min())
        top = float(h[i_hi])
        rng = top - lo
        if rng <= 2 * a_t:
            return None
        r = (price - lo) / rng
    else:
        i_lo = s + int(np.argmin(l[s:start]))
        if i_lo + 1 >= start:
            return None
        hi = float(h[i_lo:start].max())
        bot = float(l[i_lo])
        rng = hi - bot
        if rng <= 2 * a_t:
            return None
        r = (hi - price) / rng
    for f in KEY_RETR + KEY_EXT:
        if abs(r - f) * rng <= 0.4 * a_t:
            return f"{f:g} {'retracement' if f < 1 else 'extension'} of the prior swing"
    return None


def score_pattern(pt: Pattern, df: pd.DataFrame, zones: list[Zone], a: np.ndarray, p: PatternParams,
                  vp_cache: dict | None = None) -> Pattern:
    """Dopisuje konfluencje i wynik. Korzysta tylko z danych do świecy potwierdzenia."""
    t = pt.confirm_idx
    h, l = df["high"].to_numpy(dtype=float), df["low"].to_numpy(dtype=float)
    sell = pt.direction == "SELL"
    side = "supply" if sell else "demand"
    a_t = float(a[t])
    # kluczowe ceny: szczyty / dołki formacji albo D + PRZ
    if pt.family == "harmonic":
        keys = [pt.points[-1][1]]
        band = (min(pt.prz[0], keys[0]) - 0.3 * a_t, max(pt.prz[1], keys[0]) + 0.3 * a_t)
    else:
        keys = [pr for _, pr, lab in pt.points if lab and lab not in ("HL", "LH")]
        band = (min(keys) - 0.3 * a_t, max(keys) + 0.3 * a_t)
    conf, det = [], {}

    def hit(z: Zone) -> bool:
        return z.side in (side, "any") and z.active(t) and z.bot <= band[1] and z.top >= band[0]

    for src, label in (("M", "zone"), ("H1", "H1 zone"), ("user", "key zone")):
        zz = [z for z in zones if z.source == src and hit(z)]
        if zz:
            z = max(zz, key=lambda z: z.created)
            name = z.label or f"{label}"
            conf.append(f"{'supply' if sell else 'demand'} {name} {z.bot:.2f}–{z.top:.2f}" if src != "user"
                        else f"{name or 'key zone'} {z.bot:.2f}–{z.top:.2f}")
            det[f"zone_{src}"] = [round(z.bot, 2), round(z.top, 2)]
    if pt.family == "harmonic":
        X, A, B, C, D = (x[1] for x in pt.points)
        cl = fib_cluster(pt.kind, X, A, B, C, D, a_t)
        det["fib_cluster"] = cl
        if len(cl) >= 2:
            conf.append("Fib cluster at D: " + " + ".join(cl))
    start = pt.points[0][0]
    mf = _major_fib(h, l, start, keys[-1], sell, a_t)
    if mf:
        conf.append("Fib " + mf)
        det["major_fib"] = mf
    key = t - 1
    prof = None
    if vp_cache is not None and key in vp_cache:
        prof = vp_cache[key]
    elif "volume" in df.columns:
        prof = volume_profile(df, key, p.vp_lookback)
        if vp_cache is not None:
            vp_cache[key] = prof
    if prof is not None:
        near = [n for n, v in (("POC", prof.poc), ("VAH", prof.vah), ("VAL", prof.val))
                if band[0] <= v <= band[1]]
        hvn = any(lo <= band[1] and hi >= band[0] for lo, hi in prof.hvn_ranges())
        det["vp"] = {"poc": round(prof.poc, 2), "vah": round(prof.vah, 2), "val": round(prof.val, 2)}
        if near or hvn:
            conf.append("Volume Profile " + ("/".join(near) if near else "high-volume node"))
    st = _h1_structure(df, t)
    det["h1_structure"] = st
    if (sell and st == "bearish") or (not sell and st == "bullish"):
        conf.append(f"H1 structure {st}")
    pt.confluences, pt.score = conf, len(conf)
    pt.details.update(det)
    return pt


# ----------------------------------------------------------------------------- skan

def _scan_side(df: pd.DataFrame, p: PatternParams, depth: float, top: bool, a: np.ndarray) -> list[Pattern]:
    """Skan jednej strony. top=True: formacje szczytowe i niedźwiedzie harmoniczne na zwykłych cenach;
    BUY liczymy na lustrze cen (top=True na lustrze = dołki), potem odwracamy znaki."""
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    n = len(df)
    pivots, leg, ext = zigzag(h, l, a, depth)
    conf = [pv.confirmed_at for pv in pivots]
    want_chart = [k for k in p.kinds if k in CHART_KINDS]
    want_harm = [k for k in p.kinds if k in HARMONIC_KINDS]
    out: list[Pattern] = []
    pending: dict[str, dict] = {}        # klucz -> kandydat formacji klasycznej czekający na przebicie
    fired: set[str] = set()
    k = 0
    for t in range(1, n):
        while k < len(conf) and conf[k] <= t:
            k += 1
        seq = _sequence(pivots, k, t, leg, ext, h, l)
        a_t = float(a[t])
        # --- klasyczne: zbieraj kandydatów, potwierdzaj zamknięciem za neckline
        if want_chart:
            for cd in _chart_candidates(seq, a_t, p) + _wedge_candidates(seq, a_t, p):
                key = f"{cd['kind']}-{cd['pts'][0].idx}"   # rosnący prowizoryczny szczyt nadpisuje kandydata
                if key not in fired:
                    pending[key] = cd
            for key, cd in list(pending.items()):
                last = cd["last"]
                broke_up = (c[t] > cd["upper"][0] * t + cd["upper"][1] + p.eq_tol_atr * a_t) if "upper" in cd \
                    else h[t] > cd["extreme"] + p.eq_tol_atr * a_t
                if t - last.idx > p.max_break_wait or broke_up or t > cd.get("apex", np.inf):
                    pending.pop(key)
                    fired.add(key)                       # unieważniona - nie wraca
                    continue
                if t <= last.idx:
                    continue
                neck = _neck_at(cd, t)
                if c[t] < neck and c[t - 1] >= _neck_at(cd, t - 1):
                    pending.pop(key)
                    fired.add(key)
                    height = cd["height"]
                    if neck - c[t] > p.max_chase * height:
                        continue
                    entry = float(c[t])
                    sl = float(max(x.price for x in cd["pts"] if x.kind == "H") + p.sl_buf_atr * a_t)
                    if cd["kind"] == "head_shoulders":   # H&S: SL za prawym ramieniem
                        sl = float(cd["last"].price + p.sl_buf_atr * a_t)
                    if cd["kind"] == "rising_wedge":     # klin: SL nad ostatnim szczytem, cel z szerokości klina
                        sl = float(max(h[last.idx : t + 1].max(), last.price) + p.sl_buf_atr * a_t)
                    tps = [float(neck - f * height) for f in (p.wedge_tps if "upper" in cd else p.chart_tps)]
                    if sl <= entry or tps[-1] >= entry or (entry - tps[-1]) / (sl - entry) < p.min_rr:
                        continue
                    pts = [(x.idx, x.price, lab) for x, lab in zip(cd["pts"], cd["labels"])]
                    kind = cd["kind"]
                    if not top:
                        kind = {"double_top": "double_bottom", "triple_top": "triple_bottom",
                                "head_shoulders": "inv_head_shoulders", "rising_wedge": "falling_wedge"}[kind]
                        pts = [(i, pr, {"HH": "LL", "HL": "LH"}.get(lab, lab.replace("Top", "Bottom")))
                               for i, pr, lab in pts]
                    if kind not in want_chart:
                        continue
                    ni = [(i, _neck_at(cd, i)) for i in (cd["neck"][0][0], t)]
                    det = {"neckline_break": round(neck, 2)}
                    if "upper" in cd:
                        mu, bu = cd["upper"]
                        i0 = cd["pts"][0].idx
                        det["upper_line"] = [(i0, mu * i0 + bu), (t, mu * t + bu)]
                        # kontekst jak na grafice: klin po ruchu w jego stronę = odwrócenie, inaczej kontynuacja
                        j = max(0, i0 - (cd["last"].idx - i0))
                        up_before = c[j] < cd["pts"][0].price - 0.5 * height
                        det["context"] = "reversal" if up_before else "continuation"
                    out.append(Pattern(kind, "SELL", pts, t, entry, sl, tps, depth, neckline=ni,
                                       ratios={"height": round(height, 2)}, details=det))
        # --- harmoniczne niedźwiedzie (W): X szczyt, A dołek, B szczyt, C dołek, D szczyt - bieżące,
        # jeszcze niepotwierdzone ekstremum nogi C->D. Bycze liczą się tym samym kodem na lustrze cen.
        if want_harm and len(seq) >= 5 and seq[-1].confirmed_at == -1:
            X, A, B, C, D = seq[-5:]
            kinds = [x.kind for x in (X, A, B, C, D)]
            if kinds == ["H", "L", "H", "L", "H"] and D.idx >= t - 2:
                Xp, Ap, Bp, Cp, Dp = X.price, A.price, B.price, C.price, D.price
                for kind in match_harmonic(Xp, Ap, Bp, Cp, Dp, p.ratio_slack, want_harm):
                    key = f"{kind}-{X.idx}-{C.idx}"
                    if key in fired:
                        continue
                    # odrzucenie PRZ: świeca zamyka się w dół, knot od D co najmniej rej_atr
                    if not (c[t] < o[t] and Dp - c[t] >= p.rej_atr * a_t):
                        continue
                    fired.add(key)
                    lo, hi = harmonic_prz(kind, Xp, Ap, Bp, Cp)
                    entry = float(c[t])
                    sl = float(max(hi, Dp) + p.sl_buf_atr * a_t)
                    ad = abs(Dp - Ap)
                    tps = [float(Dp - f * ad) for f in p.harm_tps]
                    if sl <= entry or tps[0] >= entry or (entry - tps[-1]) / (sl - entry) < p.min_rr:
                        continue
                    r = harmonic_ratios(Xp, Ap, Bp, Cp, Dp)
                    pts = [(x.idx, x.price, lab) for x, lab in zip((X, A, B, C, D), "XABCD")]
                    out.append(Pattern(kind, "SELL", pts, t, entry, sl, tps, depth, prz=[lo, hi],
                                       ratios={k2: round(v, 3) for k2, v in r.items()}))
    return out


def _flip_pattern(pt: Pattern) -> Pattern:
    pt.direction = "BUY"
    pt.points = [(i, -pr, lab) for i, pr, lab in pt.points]
    pt.entry, pt.sl = -pt.entry, -pt.sl
    pt.tps = [-x for x in pt.tps]
    if pt.neckline:
        pt.neckline = [(i, -pr) for i, pr in pt.neckline]
    if pt.prz:
        pt.prz = [-pt.prz[1], -pt.prz[0]]
    if "neckline_break" in pt.details:
        pt.details["neckline_break"] = -pt.details["neckline_break"]
    if "upper_line" in pt.details:
        pt.details["upper_line"] = [(i, -pr) for i, pr in pt.details["upper_line"]]
    return pt


def find_patterns(df: pd.DataFrame, p: PatternParams | None = None, user_zones: list[Zone] | None = None,
                  score: bool = True) -> list[Pattern]:
    """Wszystkie formacje z historii (posortowane po świecy potwierdzenia), z konfluencjami."""
    p = p or PatternParams()
    df = df.reset_index(drop=True)
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    a = atr_array(h, l, c)
    m = _mirror(df)
    found: dict[str, Pattern] = {}
    for depth in p.depths:
        sells = _scan_side(df, p, depth, True, a)
        buys = [_flip_pattern(x) for x in _scan_side(m, p, depth, False, a)]
        for pt in sells + buys:
            found.setdefault(pt.key, pt)                     # ta sama formacja z dwóch skal = raz
    pats = sorted(found.values(), key=lambda x: (x.confirm_idx, x.kind))
    # triple top / H&S zawierają double top na tych samych ostatnich szczytach - zostaw bogatszą formację
    rich = {(x.confirm_idx, x.direction) for x in pats if x.kind not in ("double_top", "double_bottom")
            and x.family == "chart"}
    pats = [x for x in pats if not (x.kind in ("double_top", "double_bottom") and (x.confirm_idx, x.direction) in rich)]
    if "time" in df.columns:
        for x in pats:
            x.confirm_time = str(df["time"].iloc[x.confirm_idx])
    if score:
        zones = order_block_zones(df, p.zone_swing_n) + (h1_zones(df) if "time" in df.columns else []) \
            + list(user_zones or [])
        vp_cache: dict = {}
        for x in pats:
            score_pattern(x, df, zones, a, p, vp_cache)
    return pats


# ----------------------------------------------------------------------------- wynik

def simulate(df: pd.DataFrame, pt: Pattern, max_hold: int = 96) -> Pattern:
    """Pozycja od świecy po potwierdzeniu: połowa na TP1 (SL na wejście), reszta na ostatnim TP.
    Gdy SL i TP w jednej świecy - liczymy SL (konserwatywnie)."""
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    s = 1 if pt.direction == "BUY" else -1
    risk = pt.risk
    left, sl, pnl, k, exits = 1.0, pt.sl, 0.0, 0, []
    frac = 1.0 / len(pt.tps)
    end = min(len(df), pt.confirm_idx + 1 + max_hold)
    for u in range(pt.confirm_idx + 1, end):
        if (s == 1 and l[u] <= sl) or (s == -1 and h[u] >= sl):
            pnl += left * s * (sl - pt.entry)
            exits.append(("sl" if k == 0 else "be", u, sl))
            pt.outcome, pt.r, pt.exits = ("sl" if k == 0 else f"tp{k}"), pnl / risk, exits
            return pt
        while k < len(pt.tps) and ((s == 1 and h[u] >= pt.tps[k]) or (s == -1 and l[u] <= pt.tps[k])):
            f = frac if k < len(pt.tps) - 1 else left
            pnl += f * s * (pt.tps[k] - pt.entry)
            left -= f
            exits.append((f"tp{k + 1}", u, pt.tps[k]))
            k += 1
            sl = pt.entry
        if left <= 1e-9:
            pt.outcome, pt.r, pt.exits = f"tp{k}", pnl / risk, exits
            return pt
    if end - pt.confirm_idx - 1 < max_hold:
        pt.outcome, pt.r, pt.exits = "open", (pnl + left * s * (c[end - 1] - pt.entry)) / risk, exits
        return pt
    pnl += left * s * (c[end - 1] - pt.entry)
    exits.append(("timeout", end - 1, float(c[end - 1])))
    pt.outcome, pt.r, pt.exits = "timeout", pnl / risk, exits
    return pt
