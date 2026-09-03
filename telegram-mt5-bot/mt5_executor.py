"""Talks to a locally running MT5 terminal via the MetaTrader5 package.

This package only works on Windows, next to a running MT5 terminal - it is
imported lazily so the rest of the bot (parser/planner/tests) can be
developed and tested on any OS. In DRY_RUN mode this module is never
touched; every "would send" line is only logged.
"""
from __future__ import annotations

import logging
from typing import List, Optional

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

    def move_sl_to_breakeven(self, campaign: Campaign) -> None:
        mt5 = self._mt5
        positions = mt5.positions_get(symbol=self.config.symbol) or ()
        for pos in positions:
            if pos.magic != campaign.magic:
                continue
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": self.config.symbol,
                "position": pos.ticket,
                "sl": pos.price_open,
                "tp": pos.tp,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("breakeven move failed for ticket %s: %s", pos.ticket, result)
            else:
                log.info("moved SL to breakeven (%.2f) for ticket %s", pos.price_open, pos.ticket)

    def close_campaign(self, campaign: Campaign) -> None:
        mt5 = self._mt5

        for order in mt5.orders_get(symbol=self.config.symbol) or ():
            if order.magic != campaign.magic:
                continue
            result = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": order.ticket})
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("cancel pending failed for ticket %s: %s", order.ticket, result)
            else:
                log.info("cancelled pending order ticket %s", order.ticket)

        for pos in mt5.positions_get(symbol=self.config.symbol) or ():
            if pos.magic != campaign.magic:
                continue
            bid, ask = self.current_price()
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = bid if close_type == mt5.ORDER_TYPE_SELL else ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.config.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": self.config.deviation_points,
                "magic": campaign.magic,
                "comment": f"tg-{campaign.id}-close"[:31],
                "type_filling": mt5.ORDER_FILLING_RETURN,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                log.error("close failed for ticket %s: %s", pos.ticket, result)
            else:
                log.info("closed position ticket %s", pos.ticket)
