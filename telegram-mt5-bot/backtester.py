"""Pure signal-vs-price-history simulation, with NO Telegram/MT5 imports -
testable on any OS (see tests/test_backtester.py). backtest.py is the CLI
wrapper that fetches the real signal history (Telethon) and real M1 price
bars (MT5's own copy_rates_range) and calls simulate_campaign() here once
per ZONE signal, using the exact same order_planner.plan_orders() the live
bot uses and the same .env settings (lot scaling, TP mode, exit mode).

Approximations, since this works from 1-minute OHLC bars rather than tick
data (documented, not hidden - see backtest.py's docstring too):
  - A pending order "fills" the first bar whose low..high range crosses its
    entry price, at that exact entry price (no slippage/spread modeled).
  - If both SL and TP fall inside the same bar's range, SL is assumed hit
    first (the conservative assumption - avoids overstating performance).
  - EXIT_MODE=tp's basket-average breakeven check and EXIT_MODE=trailing_
    stop's stepped SL are evaluated once per bar using that bar's CLOSE
    price as "current price" (the live bot polls roughly continuously -
    once a minute is a reasonable stand-in).
  - A signal's zone/SL is anchored to the message's own timestamp; MT5 bar
    times are in the broker's server timezone, which can be a few hours
    off from Telegram's UTC message time - not corrected for here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from config import Config
from order_planner import plan_orders
from signal_parser import ZoneSignal


@dataclass
class Bar:
    time: float  # unix epoch seconds
    open: float
    high: float
    low: float
    close: float


@dataclass
class OrderResult:
    direction: str
    entry_price: float
    sl_price: float
    tp_price: float
    lot: float
    filled: bool = False
    fill_time: Optional[float] = None
    closed: bool = False
    close_time: Optional[float] = None
    close_price: Optional[float] = None
    close_reason: str = ""  # "tp" / "sl" / "breakeven" / "trailing"
    moved_to_breakeven: bool = False
    trailed: bool = False
    pips: float = 0.0
    profit: float = 0.0


@dataclass
class CampaignResult:
    signal_time: float
    direction: str
    zone_low: float
    zone_high: float
    orders: List[OrderResult] = field(default_factory=list)

    @property
    def filled_count(self) -> int:
        return sum(1 for o in self.orders if o.filled)

    @property
    def closed_count(self) -> int:
        return sum(1 for o in self.orders if o.closed)

    @property
    def total_pips(self) -> float:
        return round(sum(o.pips for o in self.orders if o.closed), 1)

    @property
    def total_profit(self) -> float:
        return round(sum(o.profit for o in self.orders if o.closed), 2)


def _close(o: OrderResult, time_: float, price: float, direction: str, pip_size: float, contract_size: float) -> None:
    o.closed = True
    o.close_time = time_
    o.close_price = price
    pips = (price - o.entry_price) / pip_size if direction == "BUY" else (o.entry_price - price) / pip_size
    o.pips = round(pips, 1)
    o.profit = round(pips * pip_size * o.lot * contract_size, 2)
    if o.moved_to_breakeven and price == o.sl_price:
        o.close_reason = "breakeven"
    elif o.trailed and price == o.sl_price:
        o.close_reason = "trailing"
    else:
        o.close_reason = "sl" if price == o.sl_price else "tp"


def simulate_campaign(
    signal_time: float,
    zone: ZoneSignal,
    bars: Sequence[Bar],
    config: Config,
    contract_size: float,
) -> CampaignResult:
    plans = plan_orders(
        zone,
        lot=config.lot_size, step=config.zone_step, pip_size=config.pip_size,
        start_tp_pips=config.start_tp_pips, tp_increment_pips=config.tp_increment_pips,
        lot_tier_orders=config.lot_tier_orders, lot_scaling_mode=config.lot_scaling_mode,
        lot_multiplier=config.lot_multiplier, tp_mode=config.tp_mode,
        tp_risk_reward_ratio=config.tp_risk_reward_ratio, exit_mode=config.exit_mode,
        zone_extend_front=config.zone_extend_front, zone_extend_back=config.zone_extend_back,
    )
    result = CampaignResult(signal_time=signal_time, direction=zone.direction, zone_low=zone.zone_low, zone_high=zone.zone_high)
    if not plans:
        return result

    shared_sl = plans[0].sl_price
    orders = [
        OrderResult(direction=p.direction, entry_price=p.entry_price, sl_price=p.sl_price, tp_price=p.tp_price, lot=p.lot)
        for p in plans
    ]
    result.orders = orders

    direction = zone.direction
    step_distance = config.trailing_stop_pips * config.pip_size
    breakeven_applied = False

    for bar in bars:
        if bar.time < signal_time:
            continue

        for o in orders:
            if not o.filled and bar.low <= o.entry_price <= bar.high:
                o.filled = True
                o.fill_time = bar.time

        open_orders = [o for o in orders if o.filled and not o.closed]
        if not open_orders:
            continue

        # 1) Resolve this bar's price action against whatever SL/TP was
        # already active BEFORE this bar - mirrors a broker-side resting
        # order executing instantly, ahead of the bot's own periodic
        # monitor tick below. Without this ordering, a bar where profit
        # happens to cross BOTH the TP level and the breakeven-move
        # trigger at once would wrongly move SL to breakeven first and
        # "steal" what should have been a TP close.
        for o in open_orders:
            hit_sl = (bar.low <= o.sl_price) if direction == "BUY" else (bar.high >= o.sl_price)
            hit_tp = config.exit_mode != "trailing_stop" and (
                (bar.high >= o.tp_price) if direction == "BUY" else (bar.low <= o.tp_price)
            )
            if hit_sl:
                _close(o, bar.time, o.sl_price, direction, config.pip_size, contract_size)
            elif hit_tp:
                _close(o, bar.time, o.tp_price, direction, config.pip_size, contract_size)

        still_open = [o for o in open_orders if not o.closed]
        if not still_open:
            continue

        # 2) The bot's own monitor-tick logic - updates SL for positions
        # that survived this bar's price action, taking effect from the
        # NEXT bar onward (same as the live bot: check_average_breakeven/
        # check_trailing_stops run on a poll loop, not synchronously with
        # the broker's own TP/SL execution).
        if config.exit_mode != "trailing_stop" and not breakeven_applied:
            total_volume = sum(o.lot for o in still_open)
            avg_entry = sum(o.entry_price * o.lot for o in still_open) / total_volume
            risk_price = (avg_entry - shared_sl) if direction == "BUY" else (shared_sl - avg_entry)
            if risk_price > 0:
                profit_price = (bar.close - avg_entry) if direction == "BUY" else (avg_entry - bar.close)
                if profit_price >= risk_price * config.risk_reward_trigger:
                    breakeven_applied = True
                    be_price = round(avg_entry, 2)
                    for o in still_open:
                        o.sl_price = be_price
                        o.moved_to_breakeven = True

        if config.exit_mode == "trailing_stop" and step_distance > 0:
            for o in still_open:
                profit_distance = (bar.close - o.entry_price) if direction == "BUY" else (o.entry_price - bar.close)
                steps = math.floor(round(profit_distance / step_distance, 6))
                if steps < 1:
                    continue
                locked = (steps - 1) * step_distance
                candidate = round(o.entry_price + locked, 2) if direction == "BUY" else round(o.entry_price - locked, 2)
                improved = candidate > o.sl_price if direction == "BUY" else candidate < o.sl_price
                if improved:
                    o.sl_price = candidate
                    o.trailed = True

    return result
