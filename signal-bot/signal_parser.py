"""Parsowanie wiadomości z kanału: sygnały oraz aktualizacje (TP / SL hit)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUM = r"\d+(?:[.,]\d+)?"
UNIT = r"(?:pips?|pipsów|pipsow|pipsy|pkt|points?)"

CURRENCIES = (
    "USD|EUR|GBP|JPY|CHF|AUD|NZD|CAD|XAU|XAG|BTC|ETH|SGD|NOK|SEK|PLN|ZAR|MXN|TRY|HKD|CNH"
)
INSTRUMENTS = (
    "US30|NAS100|US100|USTEC|SPX500|US500|GER40|GER30|DE40|UK100|JP225|DJ30|"
    "USOIL|UKOIL|WTI|GOLD|SILVER"
)
SYMBOL_RE = re.compile(
    rf"(?<![A-Za-z])((?:{CURRENCIES})\s?/?\s?(?:{CURRENCIES})|{INSTRUMENTS})(?![A-Za-z])",
    re.I,
)
SYMBOL_ALIASES = {"GOLD": "XAUUSD", "SILVER": "XAGUSD", "USTEC": "NAS100", "US100": "NAS100"}

DIRECTION_RE = re.compile(r"\b(BUY|SELL|LONG|SHORT|KUPNO|KUP|SPRZEDA[ŻZ]|SPRZEDAJ)\b", re.I)

# "TP1: 2350", "TP 2 - 2360", "TP3 2370", "TP: 1.0850", "TP1: 30 pips"
TP_VALUE_RE = re.compile(
    rf"\bT\.?P\.?(?:\s?(?P<idx>\d{{1,2}})(?=\s*[:=\-–@)]|\s+\d))?\s*[:=\-–@)]*\s*"
    rf"(?P<val>{NUM})(?P<unit>\s*{UNIT})?",
    re.I,
)
SL_VALUE_RE = re.compile(
    rf"\b(?:SL|S/L|stop\s*loss)\s*[:=\-–@]*\s*(?P<val>{NUM})(?P<unit>\s*{UNIT})?",
    re.I,
)
ENTRY_RE = re.compile(
    rf"(?:\b(?:entry|enter|wej[śs]cie|open|cena|price)\b(?:\s*(?:price|zone|strefa))?|@)"
    rf"\s*[:=\-–@]*\s*(?P<val>{NUM})",
    re.I,
)
ENTRY_AFTER_DIRECTION_RE = re.compile(
    rf"\b(?:BUY|SELL|LONG|SHORT|KUPNO|SPRZEDA[ŻZ])\b\s*(?:now|limit|stop|teraz)?\s*[:@\-–]?\s*(?P<val>{NUM})",
    re.I,
)

HIT = (
    r"(?:✅|✔️|✔|☑️|hit|zaliczon\w*|osi[ąa]gni[ęe]t\w*|trafion\w*|z[łl]apan\w*|done|reached|"
    r"smash\w*|achieved|secured|🎯|💰|🔥|🤑)"
)
TP_HIT_RE = re.compile(
    rf"\bT\.?P\.?\s?(?P<idx>\d{{1,2}})\b[^\n]*?{HIT}|{HIT}[^\n]{{0,15}}?\bT\.?P\.?\s?(?P<idx2>\d{{1,2}})\b",
    re.I,
)
ALL_TP_RE = re.compile(r"\b(?:all|wszystkie)\s+(?:tps?|targets?|cele|take\s*profits?)\b", re.I)
SL_HIT_RE = re.compile(
    r"\b(?:SL|S/L|stop\s*loss)\b[^\n]*?(?:hit|trafion\w*|z[łl]apan\w*|zaliczon\w*|aktywowan\w*|"
    r"reached|❌|🛑|🔴)|(?:❌|🛑|🔴)[^\n]{0,10}?\b(?:SL|S/L|stop\s*loss)\b",
    re.I,
)
BREAKEVEN_RE = re.compile(r"\b(?:BE|break\s*even|breakeven|na\s+zero)\b", re.I)
PIPS_RE = re.compile(rf"\+?\s?(?P<val>{NUM})\s*{UNIT}", re.I)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def normalize_symbol(raw: str) -> str:
    sym = re.sub(r"[\s/]", "", raw).upper()
    return SYMBOL_ALIASES.get(sym, sym)


def find_symbol(text: str) -> str | None:
    m = SYMBOL_RE.search(text)
    return normalize_symbol(m.group(1)) if m else None


@dataclass
class Signal:
    symbol: str
    direction: str
    strategy: str | None
    entry: float | None
    sl: float | None
    sl_is_pips: bool
    # lista (wartość, czy_w_pipsach) — indeks 0 = TP1
    tps: list[tuple[float, bool]] = field(default_factory=list)


@dataclass
class Update:
    tp_hits: set[int] = field(default_factory=set)
    all_tps: bool = False
    sl_hit: bool = False
    breakeven: bool = False
    pips: float | None = None  # pipsy podane wprost w wiadomości
    symbol: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.tp_hits or self.all_tps or self.sl_hit)


class StrategyMatcher:
    """Rozpoznaje numer strategii. Wzorzec musi mieć jedną grupę z numerem/nazwą."""

    DEFAULT = r"strateg\w*\s*(?:nr\.?|no\.?|#|numer)?\s*(\d+)|#s(?:trat)?(\d+)\b"

    def __init__(self, pattern: str | None = None):
        self.re = re.compile(pattern or self.DEFAULT, re.I)

    def find(self, text: str) -> str | None:
        m = self.re.search(text)
        if not m:
            return None
        for g in m.groups():
            if g:
                return g
        return None


def parse_signal(text: str, strategies: StrategyMatcher) -> Signal | None:
    symbol = find_symbol(text)
    dmatch = DIRECTION_RE.search(text)
    tp_matches = list(TP_VALUE_RE.finditer(text))
    if not (symbol and dmatch and tp_matches):
        return None

    d = dmatch.group(1).upper()
    direction = "BUY" if d in ("BUY", "LONG", "KUPNO", "KUP") else "SELL"

    tps: dict[int, tuple[float, bool]] = {}
    seq = 0
    for m in tp_matches:
        seq += 1
        idx = int(m.group("idx")) if m.group("idx") else seq
        seq = idx
        tps.setdefault(idx, (_num(m.group("val")), bool(m.group("unit"))))
    tp_list = [tps[i] for i in sorted(tps)]

    sl, sl_is_pips = None, False
    if sm := SL_VALUE_RE.search(text):
        sl, sl_is_pips = _num(sm.group("val")), bool(sm.group("unit"))

    entry = None
    if em := ENTRY_RE.search(text):
        entry = _num(em.group("val"))
    elif em := ENTRY_AFTER_DIRECTION_RE.search(text):
        entry = _num(em.group("val"))

    if sl is None and entry is None:
        return None  # zbyt mało danych, prawdopodobnie to nie jest sygnał

    return Signal(
        symbol=symbol,
        direction=direction,
        strategy=strategies.find(text),
        entry=entry,
        sl=sl,
        sl_is_pips=sl_is_pips,
        tps=tp_list,
    )


def parse_update(text: str) -> Update:
    u = Update(symbol=find_symbol(text))
    for m in TP_HIT_RE.finditer(text):
        u.tp_hits.add(int(m.group("idx") or m.group("idx2")))
    u.all_tps = bool(ALL_TP_RE.search(text))
    u.breakeven = bool(BREAKEVEN_RE.search(text))
    u.sl_hit = bool(SL_HIT_RE.search(text)) and not u.breakeven
    if u.tp_hits or u.all_tps:
        vals = [_num(m.group("val")) for m in PIPS_RE.finditer(text)]
        if vals:
            u.pips = max(vals)
    return u


def diff_updates(old: Update, new: Update) -> Update:
    """Dla edytowanych sygnałów: tylko to, co doszło po edycji."""
    return Update(
        tp_hits=new.tp_hits - old.tp_hits,
        all_tps=new.all_tps and not old.all_tps,
        sl_hit=new.sl_hit and not old.sl_hit,
        breakeven=new.breakeven,
        pips=new.pips if new.pips != old.pips else None,
        symbol=new.symbol,
    )


# --- pipsy ----------------------------------------------------------------

INDEX_LIKE = {"US30", "NAS100", "SPX500", "US500", "GER40", "GER30", "DE40", "UK100", "JP225", "DJ30"}


def pip_size(symbol: str, overrides: dict[str, float] | None = None) -> float:
    if overrides and symbol in overrides:
        return overrides[symbol]
    if symbol.startswith("XAU"):
        return 0.1
    if symbol.startswith("XAG"):
        return 0.01
    if symbol in INDEX_LIKE or symbol.startswith(("BTC", "ETH")):
        return 1.0
    if symbol in ("USOIL", "UKOIL", "WTI"):
        return 0.01
    if "JPY" in symbol:
        return 0.01
    return 0.0001


def tp_pips(
    symbol: str,
    entry: float | None,
    tps: list[tuple[float, bool]],
    tp_index: int,
    overrides: dict[str, float] | None = None,
) -> float:
    """Pipsy dla TP o numerze tp_index (1-based)."""
    if tp_index < 1 or not tps:
        return 0.0
    value, is_pips = tps[min(tp_index, len(tps)) - 1]
    if is_pips:
        return value
    if entry is None:
        return 0.0
    return round(abs(value - entry) / pip_size(symbol, overrides), 1)


def sl_pips(
    symbol: str,
    entry: float | None,
    sl: float | None,
    sl_is_pips: bool,
    overrides: dict[str, float] | None = None,
) -> float:
    if sl is None:
        return 0.0
    if sl_is_pips:
        return sl
    if entry is None:
        return 0.0
    return round(abs(entry - sl) / pip_size(symbol, overrides), 1)
