"""Parses Polish-language Telegram trading signals like the ones in the
'PREMIUM SIGNALS (TAKE PROFIT)' channel:

    TAKE PROFIT: Kierunek: Buy Gold
    Strefa: 4419-14
    SL: 60 pips

    TAKE PROFIT: +70 pips SL na BE juz mozliwy...

    TAKE PROFIT: +140 pips Zamykam calosc. Podsylajcie swoje wyniki!
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalType(Enum):
    ZONE = "zone"           # a new buy/sell zone to open orders in
    ADD_TO_ZONE = "add_to_zone"  # "dolóz do pozycji" - a new zone/SL but no
                             # direction of its own; inferred from the most
                             # recently active campaign (see main.py)
    BREAKEVEN = "breakeven"  # move SL to entry on the active zone
    CLOSE_ALL = "close_all"  # close everything for the active zone
    PARTIAL_INFO = "partial_info"  # profit update, no automated action
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ZoneSignal:
    direction: str  # "BUY" or "SELL"
    zone_low: float
    zone_high: float
    sl_pips: float


@dataclass(frozen=True)
class AddToZoneSignal:
    """Same shape as ZoneSignal minus direction - "dolóz do pozycji"
    messages give a new zone/SL but don't repeat "Kierunek: Buy/Sell Gold",
    so the direction has to come from context (main.py infers it from the
    most recently active campaign for the symbol)."""
    zone_low: float
    zone_high: float
    sl_pips: float


@dataclass(frozen=True)
class ParsedMessage:
    type: SignalType
    zone: Optional[ZoneSignal] = None
    add_to_zone: Optional[AddToZoneSignal] = None
    profit_pips: Optional[float] = None
    raw_text: str = ""


_DIRECTION_RE = re.compile(r"kierunek\s*:?\s*(buy|sell)\s*gold", re.IGNORECASE)
_ZONE_RE = re.compile(r"strefa\s*:\s*(\d+)\s*-\s*(\d+)", re.IGNORECASE)
_SL_RE = re.compile(r"\bsl\s*:\s*(\d+(?:[.,]\d+)?)\s*pips?", re.IGNORECASE)
_PROFIT_RE = re.compile(r"([+-]\s?\d+(?:[.,]\d+)?)\s*pips?", re.IGNORECASE)


def _strip_diacritics(text: str) -> str:
    # "ł"/"Ł" don't decompose via NFKD (they're base letters, not a letter
    # + combining mark), so they need an explicit swap before stripping.
    text = text.replace("ł", "l").replace("Ł", "L")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _combine_zone_prices(a: str, b: str) -> tuple[float, float]:
    """'4425-20' -> (4420.0, 4425.0); '4430-35' -> (4430.0, 4435.0);
    '4397-02' -> (4397.0, 4402.0).

    The second number is the last N digits of the real price - it replaces
    the tail of the first number rather than being read as its own price.
    Picks whichever hundred (b's block, one below, or one above) makes the
    combined price closest to `a`, so a zone that crosses a round hundred
    (...97 -> ...02) resolves the right way instead of just concatenating
    a's leading digits with b - a live signal ("Strefa: 4397-02") once got
    misread as 4302 that way, turning a $5 zone into a $100 one and firing
    ~200 orders instead of ~11.
    """
    if len(b) >= len(a):
        p1, p2 = float(a), float(b)
        return (p1, p2) if p1 <= p2 else (p2, p1)

    a_val = float(a)
    scale = 10 ** len(b)
    base = (int(a_val) // scale) * scale
    b_val = float(b)
    candidates = [base + b_val - scale, base + b_val, base + b_val + scale]
    b_full = min(candidates, key=lambda c: abs(c - a_val))

    p1, p2 = a_val, b_full
    return (p1, p2) if p1 <= p2 else (p2, p1)


def _extract_profit(plain_text: str) -> Optional[float]:
    match = _PROFIT_RE.search(plain_text)
    if not match:
        return None
    return float(match.group(1).replace(" ", "").replace(",", "."))


def parse(raw_text: str) -> ParsedMessage:
    text = raw_text.strip()
    plain = _strip_diacritics(text.lower())

    if "zamykam calosc" in plain or "zamykam cala pozycje" in plain:
        return ParsedMessage(type=SignalType.CLOSE_ALL, profit_pips=_extract_profit(plain), raw_text=text)

    if "sl na be" in plain or "sl->be" in plain or "sl na breakeven" in plain:
        return ParsedMessage(type=SignalType.BREAKEVEN, profit_pips=_extract_profit(plain), raw_text=text)

    direction_match = _DIRECTION_RE.search(text)
    zone_match = _ZONE_RE.search(text)
    sl_match = _SL_RE.search(text)
    add_to_position = "doloz do pozycji" in plain

    if zone_match and sl_match and (direction_match or add_to_position):
        zone_low, zone_high = _combine_zone_prices(zone_match.group(1), zone_match.group(2))
        sl_pips = float(sl_match.group(1).replace(",", "."))
        if direction_match:
            return ParsedMessage(
                type=SignalType.ZONE,
                zone=ZoneSignal(direction=direction_match.group(1).upper(), zone_low=zone_low, zone_high=zone_high, sl_pips=sl_pips),
                raw_text=text,
            )
        return ParsedMessage(
            type=SignalType.ADD_TO_ZONE,
            add_to_zone=AddToZoneSignal(zone_low=zone_low, zone_high=zone_high, sl_pips=sl_pips),
            raw_text=text,
        )

    profit = _extract_profit(plain)
    if profit is not None:
        return ParsedMessage(type=SignalType.PARTIAL_INFO, profit_pips=profit, raw_text=text)

    return ParsedMessage(type=SignalType.UNKNOWN, raw_text=text)
