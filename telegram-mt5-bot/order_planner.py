"""Turns a parsed zone signal into a ladder of individual pending orders:
one order every `step` dollars across the zone, each 0.01 lot, with a TP
ladder that starts at `start_tp_pips` for the lowest price in the zone and
grows by `tp_increment_pips` for each order above it. SL is a single shared
price for the whole grid - sl_pips away from the zone's worst entry (the
lowest price for a BUY zone, the highest for a SELL zone) - not a separate
SL measured from each order's own entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from signal_parser import ZoneSignal


@dataclass(frozen=True)
class OrderPlan:
    direction: str  # "BUY" or "SELL"
    entry_price: float
    sl_price: float
    tp_price: float
    tp_pips: float
    lot: float


def generate_price_levels(zone_low: float, zone_high: float, step: float) -> List[float]:
    """Prices from zone_low to zone_high (inclusive) spaced `step` apart.

    Uses Decimal so 0.5 increments over a $5 zone don't drift into
    4420.4999999999995-style floats.
    """
    if step <= 0:
        raise ValueError("step must be > 0")

    low = Decimal(str(zone_low))
    high = Decimal(str(zone_high))
    if low > high:
        low, high = high, low
    step_d = Decimal(str(step))

    levels = []
    current = low
    tolerance = step_d / Decimal(1000)
    while current <= high + tolerance:
        levels.append(float(current))
        current += step_d
    return levels


def plan_orders(
    zone: ZoneSignal,
    lot: float,
    step: float,
    pip_size: float,
    start_tp_pips: float,
    tp_increment_pips: float,
) -> List[OrderPlan]:
    levels = generate_price_levels(zone.zone_low, zone.zone_high, step)

    if zone.direction == "BUY":
        shared_sl_price = round(min(levels) - zone.sl_pips * pip_size, 2)
    elif zone.direction == "SELL":
        shared_sl_price = round(max(levels) + zone.sl_pips * pip_size, 2)
    else:
        raise ValueError(f"unknown direction: {zone.direction}")

    plans: List[OrderPlan] = []
    for i, entry in enumerate(levels):
        tp_pips = start_tp_pips + i * tp_increment_pips
        tp_price = entry + tp_pips * pip_size if zone.direction == "BUY" else entry - tp_pips * pip_size

        plans.append(
            OrderPlan(
                direction=zone.direction,
                entry_price=round(entry, 2),
                sl_price=shared_sl_price,
                tp_price=round(tp_price, 2),
                tp_pips=tp_pips,
                lot=lot,
            )
        )
    return plans
