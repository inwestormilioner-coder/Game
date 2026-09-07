"""Turns a parsed zone signal into a ladder of individual pending orders:
one order every `step` dollars across the zone, with a TP ladder that
starts at `start_tp_pips` for the lowest price in the zone and grows by
`tp_increment_pips` for each order above it. SL is a single shared price
for the whole grid - sl_pips away from the zone's worst entry (the lowest
price for a BUY zone, the highest for a SELL zone) - not a separate SL
measured from each order's own entry.

Lot size grows the closer an entry is to that shared SL: every
`lot_tier_orders` orders, counted starting from the entry furthest from
SL, size increases by one more `lot` increment - e.g. with lot=0.01 and
lot_tier_orders=3 across 10 orders: 0.01,0.01,0.01,0.02,0.02,0.02,0.03,
0.03,0.03,0.04.
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


def _lot_tiers_by_distance_to_sl(levels: List[float], shared_sl_price: float, lot_tier_orders: int) -> List[int]:
    """Returns, for each index into `levels`, which tier (0, 1, 2, ...) it
    falls into - tier 0 is the `lot_tier_orders` entries furthest from
    shared_sl_price, tier 1 the next `lot_tier_orders` closer, and so on,
    ending with the entries closest to SL in the highest tier."""
    order_by_distance_desc = sorted(
        range(len(levels)), key=lambda i: abs(levels[i] - shared_sl_price), reverse=True
    )
    tier_of_index = [0] * len(levels)
    for rank, idx in enumerate(order_by_distance_desc):
        tier_of_index[idx] = rank // lot_tier_orders
    return tier_of_index


def plan_orders(
    zone: ZoneSignal,
    lot: float,
    step: float,
    pip_size: float,
    start_tp_pips: float,
    tp_increment_pips: float,
    lot_tier_orders: int = 3,
) -> List[OrderPlan]:
    levels = generate_price_levels(zone.zone_low, zone.zone_high, step)

    if zone.direction == "BUY":
        shared_sl_price = round(min(levels) - zone.sl_pips * pip_size, 2)
    elif zone.direction == "SELL":
        shared_sl_price = round(max(levels) + zone.sl_pips * pip_size, 2)
    else:
        raise ValueError(f"unknown direction: {zone.direction}")

    tier_of_index = _lot_tiers_by_distance_to_sl(levels, shared_sl_price, lot_tier_orders)

    plans: List[OrderPlan] = []
    for i, entry in enumerate(levels):
        tp_pips = start_tp_pips + i * tp_increment_pips
        tp_price = entry + tp_pips * pip_size if zone.direction == "BUY" else entry - tp_pips * pip_size
        order_lot = round(lot * (tier_of_index[i] + 1), 2)

        plans.append(
            OrderPlan(
                direction=zone.direction,
                entry_price=round(entry, 2),
                sl_price=shared_sl_price,
                tp_price=round(tp_price, 2),
                tp_pips=tp_pips,
                lot=order_lot,
            )
        )
    return plans
