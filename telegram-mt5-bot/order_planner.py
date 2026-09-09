"""Turns a parsed zone signal into a ladder of individual pending orders:
one order every `step` dollars across the zone. SL is a single shared
price for the whole grid - sl_pips away from the zone's worst entry (the
lowest price for a BUY zone, the highest for a SELL zone) - not a separate
SL measured from each order's own entry.

When `exit_mode` is "tp" (default), each order gets a fixed TP computed one
of two ways (`tp_mode`):
  "ladder" (default) - starts at `start_tp_pips` for the lowest price in
    the zone and grows by `tp_increment_pips` for each order above it,
    regardless of where SL is.
  "risk_reward" - each order's TP is `tp_risk_reward_ratio` times THAT
    order's own distance to the shared SL (1.0 = 1:1) - since SL is one
    fixed price but every entry sits at a different distance from it, this
    makes TP grow automatically the further an entry is from SL, without
    picking pip numbers by hand.

When `exit_mode` is "trailing_stop", no TP is set at all (tp_price=0,
meaning "none" in MT5) - the position is meant to be closed by a
continuously trailing SL managed elsewhere (see Mt5Executor.check_trailing_stops),
not a fixed profit target.

The order grid can extend past the signal's own zone on both ends without
moving SL (SL is anchored to the signal's zone_low/zone_high, computed
before any extension is applied):
  zone_extend_front (dollars) - extra orders just past the zone's edge
    CLOSEST to where price currently sits (highest price of a BUY zone,
    lowest of a SELL zone) - catches a fill that the raw signal price
    narrowly misses due to spread.
  zone_extend_back (dollars) - extra orders past the zone's edge FURTHEST
    from price / closest to SL (lowest price of a BUY zone, highest of a
    SELL zone) - widens the grid deeper into the zone.
Both default to 0 (no extension, i.e. exactly the signal's own zone).

Lot size grows the closer an entry is to that shared SL: every
`lot_tier_orders` orders, counted starting from the entry furthest from
SL, size increases one more tier (`lot_scaling_mode`):
  "additive" (default) - +1 more `lot` increment per tier, e.g. with
    lot=0.01 and lot_tier_orders=3 across 10 orders:
    0.01,0.01,0.01,0.02,0.02,0.02,0.03,0.03,0.03,0.04.
  "multiplier" - each tier is `lot_multiplier` times the previous one
    (compounding), e.g. lot=0.1, lot_multiplier=1.2, lot_tier_orders=3:
    0.1,0.1,0.1,0.12,0.12,0.12,0.14,0.14,0.14,0.17 (rounded to 2dp per step).
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
    lot_scaling_mode: str = "additive",
    lot_multiplier: float = 1.2,
    tp_mode: str = "ladder",
    tp_risk_reward_ratio: float = 1.0,
    exit_mode: str = "tp",
    zone_extend_front: float = 0.0,
    zone_extend_back: float = 0.0,
) -> List[OrderPlan]:
    if zone.direction == "BUY":
        shared_sl_price = round(zone.zone_low - zone.sl_pips * pip_size, 2)
        grid_low = zone.zone_low - zone_extend_back
        grid_high = zone.zone_high + zone_extend_front
    elif zone.direction == "SELL":
        shared_sl_price = round(zone.zone_high + zone.sl_pips * pip_size, 2)
        grid_low = zone.zone_low - zone_extend_front
        grid_high = zone.zone_high + zone_extend_back
    else:
        raise ValueError(f"unknown direction: {zone.direction}")

    levels = generate_price_levels(grid_low, grid_high, step)
    # A large enough extension could in principle push an entry to or past
    # SL (which stays anchored to the signal's own zone) - drop any such
    # entry rather than plan a nonsensical order.
    if zone.direction == "BUY":
        levels = [lv for lv in levels if lv > shared_sl_price]
    else:
        levels = [lv for lv in levels if lv < shared_sl_price]

    tier_of_index = _lot_tiers_by_distance_to_sl(levels, shared_sl_price, lot_tier_orders)

    plans: List[OrderPlan] = []
    for i, entry in enumerate(levels):
        if exit_mode == "trailing_stop":
            tp_pips = 0.0
            tp_price = 0.0
        else:
            if tp_mode == "risk_reward":
                tp_distance = abs(entry - shared_sl_price) * tp_risk_reward_ratio
                tp_pips = round(tp_distance / pip_size, 1)
            else:
                tp_pips = start_tp_pips + i * tp_increment_pips
                tp_distance = tp_pips * pip_size
            tp_price = entry + tp_distance if zone.direction == "BUY" else entry - tp_distance

        tier = tier_of_index[i]
        if lot_scaling_mode == "multiplier":
            order_lot = round(lot * (lot_multiplier ** tier), 2)
        else:
            order_lot = round(lot * (tier + 1), 2)

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
