"""Talks to a locally running MT5 terminal via the MetaTrader5 package.

This package only works on Windows, next to a running MT5 terminal - it is
imported lazily so the rest of the bot (parser/planner/tests) can be
developed and tested on any OS. In DRY_RUN mode this module is never
touched; every "would send" line is only logged.
"""
from __future__ import annotations

import logging
from typing import List

from campaign_store import Campaign
from config import Config
from order_planner import OrderPlan

log = logging.getLogger("mt5_executor")


class Mt5Executor:
    def __init__(self, config: Config):
        self.config = config
        self._mt5 = None

    def connect(self) -> None:
        import MetaTrader5 as mt5  # noqa: N814 - package name

        self._mt5 = mt5
        kwargs = {}
        if self.config.mt5_path:
            kwargs["path"] = self.config.mt5_path
        if self.config.mt5_login:
            kwargs["login"] = self.config.mt5_login
            kwargs["password"] = self.config.mt5_password
            kwargs["server"] = self.config.mt5_server

        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

        if not mt5.symbol_select(self.config.symbol, True):
            raise RuntimeError(f"could not select symbol {self.config.symbol}")

        log.info("Connected to MT5, symbol=%s", self.config.symbol)

    def shutdown(self) -> None:
        if self._mt5:
            self._mt5.shutdown()

    def current_price(self) -> tuple[float, float]:
        """Returns (bid, ask) for the configured symbol."""
        tick = self._mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            raise RuntimeError(f"no tick data for {self.config.symbol}")
        return tick.bid, tick.ask

    def _order_type_for(self, direction: str, entry_price: float, bid: float, ask: float) -> int:
        mt5 = self._mt5
        if direction == "BUY":
            return mt5.ORDER_TYPE_BUY_LIMIT if entry_price < ask else mt5.ORDER_TYPE_BUY_STOP
        return mt5.ORDER_TYPE_SELL_LIMIT if entry_price > bid else mt5.ORDER_TYPE_SELL_STOP

    def place_zone_orders(self, plans: List[OrderPlan], campaign: Campaign) -> List[int]:
        """Sends one pending order per plan, tagged with campaign.magic.
        Returns the list of ticket numbers that were successfully placed."""
        mt5 = self._mt5
        bid, ask = self.current_price()
        tickets: List[int] = []

        for plan in plans:
            order_type = self._order_type_for(plan.direction, plan.entry_price, bid, ask)
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": self.config.symbol,
                "volume": plan.lot,
                "type": order_type,
                "price": plan.entry_price,
                "sl": plan.sl_price,
                "tp": plan.tp_price,
                "deviation": self.config.deviation_points,
                "magic": campaign.magic,
                "comment": f"tg-{campaign.id}"[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_RETURN,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("order_send failed for %.2f: %s", plan.entry_price, result)
                continue
            tickets.append(result.order)
            log.info(
                "placed %s @ %.2f sl=%.2f tp=%.2f (%.0f pips) ticket=%s",
                plan.direction, plan.entry_price, plan.sl_price, plan.tp_price, plan.tp_pips, result.order,
            )

        return tickets

    def check_average_breakeven(self, campaign: Campaign, risk_reward_trigger: float) -> bool:
        """Own SL management (channel's "SL na BE" messages are ignored -
        see main.py): once the whole basket's floating profit reaches
        risk_reward_trigger * initial risk (1.0 = 1:1), move every open
        position's SL to the basket's volume-weighted average entry price -
        not each position's own entry. Returns True if it just applied.
        Idempotent: campaign.breakeven_applied guards against reapplying.
        """
        if campaign.breakeven_applied or campaign.sl_pips <= 0:
            return False

        mt5 = self._mt5
        positions = [p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic]
        if not positions:
            return False

        total_volume = sum(p.volume for p in positions)
        avg_entry = sum(p.price_open * p.volume for p in positions) / total_volume
        risk_price = campaign.sl_pips * self.config.pip_size

        bid, ask = self.current_price()
        profit_price = (bid - avg_entry) if campaign.direction == "BUY" else (avg_entry - ask)

        if profit_price < risk_price * risk_reward_trigger:
            return False

        avg_entry = round(avg_entry, 2)
        for pos in positions:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": self.config.symbol,
                "position": pos.ticket,
                "sl": avg_entry,
                "tp": pos.tp,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("average breakeven move failed for ticket %s: %s", pos.ticket, result)
            else:
                log.info("moved SL to basket average %.2f for ticket %s", avg_entry, pos.ticket)

        return True

    def campaign_has_open_trades(self, campaign: Campaign) -> bool:
        """True while a campaign still has pending orders or open positions
        in MT5. The bot never closes a campaign itself (the channel's
        "Zamykam calosc" is ignored too - exits happen only via each
        order's own TP or its SL) - this is just used to know when a
        campaign is finished so it can stop being polled/tracked."""
        mt5 = self._mt5
        orders = [o for o in (mt5.orders_get(symbol=self.config.symbol) or ()) if o.magic == campaign.magic]
        if orders:
            return True
        positions = [p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic]
        return bool(positions)
