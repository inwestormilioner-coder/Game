"""Talks to a locally running MT5 terminal via the MetaTrader5 package.

This package only works on Windows, next to a running MT5 terminal - it is
imported lazily so the rest of the bot (parser/planner/tests) can be
developed and tested on any OS. In DRY_RUN mode this module is never
touched; every "would send" line is only logged.

Trade-modifying calls (opening orders, changing SL) do NOT go through
mt5.order_send() directly - some brokers/terminal builds silently reject
order_send() from the external Python API (retcode 10027 "AutoTrading
disabled by client") even though the terminal's own "Algo Trading" toggle
is on and manual trades work fine. Instead this writes a plain-text command
file into MT5's shared "Common\\Files" folder, which the companion
TelegramBridgeEA.mq5 (attached to a chart inside the terminal) picks up and
executes with native OrderSend() calls - the same trading path a human
clicking "New Order" uses, unaffected by that restriction. All read-only
calls (prices, positions, orders, terminal state) still go straight through
the Python API, which works fine either way - see mt5_expert/README.md.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
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
        log.info("EA bridge folder: %s", self._bridge_dir())

    def shutdown(self) -> None:
        if self._mt5:
            self._mt5.shutdown()

    def current_price(self) -> tuple[float, float]:
        """Returns (bid, ask) for the configured symbol."""
        tick = self._mt5.symbol_info_tick(self.config.symbol)
        if tick is None:
            raise RuntimeError(f"no tick data for {self.config.symbol}")
        return tick.bid, tick.ask

    def is_trading_allowed(self) -> bool:
        """False when MT5's "Algo Trading" toggle is off. Kept as an early,
        loud warning for the common case, even though actual order placement
        no longer depends on it directly (the EA does) - Algo Trading off
        also blocks EAs from trading, so it's still worth flagging."""
        info = self._mt5.terminal_info()
        return bool(info and info.trade_allowed)

    def _bridge_dir(self) -> Path:
        """MT5's shared "Common\\Files" folder (same for every terminal
        install on this machine), where TelegramBridgeEA.mq5 - attached to
        a chart with FILE_COMMON file access - looks for command files."""
        info = self._mt5.terminal_info()
        bridge_dir = Path(info.commondata_path) / "Files" / "tg_bridge"
        bridge_dir.mkdir(parents=True, exist_ok=True)
        return bridge_dir

    def _write_command(self, name_prefix: str, lines: List[str]) -> Path:
        """Writes via a temp file + atomic rename, so the EA (polling for
        *.txt files) never sees a command file mid-write - a real, observed
        failure mode: the EA read a partially-flushed file and only acted
        on the first few ORDER= lines of an 11-line zone."""
        path = self._bridge_dir() / f"{name_prefix}_{int(time.time() * 1000)}.txt"
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text("\n".join(lines) + "\n", encoding="ascii")
        tmp_path.replace(path)
        return path

    def place_zone_orders(self, plans: List[OrderPlan], campaign: Campaign) -> List[int]:
        """Queues one OPEN_ORDERS command for TelegramBridgeEA to place all
        of a zone's pending orders. Doesn't call order_send() itself - see
        module docstring. Returns [] (no tickets available immediately);
        campaign_has_open_trades() picks up what the EA actually placed."""
        if not self.is_trading_allowed():
            log.info(
                "note: the Python API reports Algo Trading as OFF - this reading isn't always "
                "accurate (TelegramBridgeEA trades independently of it); check the EA's own "
                "Eksperci log if these orders don't show up in MT5."
            )

        comment = f"tg-{campaign.id}"[:31]
        lines = [
            "TYPE=OPEN_ORDERS",
            f"MAGIC={campaign.magic}",
            f"SYMBOL={self.config.symbol}",
            f"COMMENT={comment}",
            f"DEVIATION={self.config.deviation_points}",
            f"COUNT={len(plans)}",
        ]
        for plan in plans:
            lines.append(f"ORDER={plan.direction},{plan.entry_price},{plan.sl_price},{plan.tp_price},{plan.lot}")

        path = self._write_command(f"orders_{campaign.id}", lines)
        log.info("queued %d orders for EA bridge (campaign %s) -> %s", len(plans), campaign.id, path.name)
        return []

    def check_average_breakeven(self, campaign: Campaign, risk_reward_trigger: float) -> bool:
        """Own SL management (channel's "SL na BE" messages are ignored -
        see main.py): once the whole basket's floating profit reaches
        risk_reward_trigger * initial risk (1.0 = 1:1), queues a MODIFY_SL
        command for TelegramBridgeEA to move every open position's SL to
        the basket's volume-weighted average entry price - not each
        position's own entry. Returns True once queued. Idempotent:
        campaign.breakeven_applied guards against reapplying.

        Risk is measured from the grid's single shared SL price (all
        positions in a campaign are opened with the same SL - see
        order_planner.plan_orders), read back from a live position rather
        than recomputed from sl_pips: since entries fill at different times,
        the average entry of currently-open positions moves, so the
        avg_entry-to-shared_sl distance isn't a fixed number of pips.
        """
        if campaign.breakeven_applied:
            return False

        mt5 = self._mt5
        positions = [p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic]
        if not positions:
            return False

        total_volume = sum(p.volume for p in positions)
        avg_entry = sum(p.price_open * p.volume for p in positions) / total_volume
        shared_sl = positions[0].sl
        risk_price = (avg_entry - shared_sl) if campaign.direction == "BUY" else (shared_sl - avg_entry)
        if risk_price <= 0:
            return False

        bid, ask = self.current_price()
        profit_price = (bid - avg_entry) if campaign.direction == "BUY" else (avg_entry - ask)

        if profit_price < risk_price * risk_reward_trigger:
            return False

        avg_entry = round(avg_entry, 2)
        lines = [
            "TYPE=MODIFY_SL",
            f"MAGIC={campaign.magic}",
            f"SYMBOL={self.config.symbol}",
            f"NEW_SL={avg_entry}",
        ]
        path = self._write_command(f"modify_{campaign.id}", lines)
        log.info("queued SL update to basket average %.2f for campaign %s -> %s", avg_entry, campaign.id, path.name)
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

    def check_bridge_backlog(self, max_age_seconds: float = 30) -> None:
        """Warns if command files are piling up unprocessed in the bridge
        folder - the most likely cause is TelegramBridgeEA not being
        attached/running on a chart."""
        bridge_dir = self._bridge_dir()
        now = time.time()
        stale = [p for p in bridge_dir.glob("*.txt") if now - p.stat().st_mtime > max_age_seconds]
        if not stale:
            return

        log.warning("=" * 70)
        log.warning(
            "%d command file(s) in the EA bridge folder are still unprocessed after %.0fs.",
            len(stale), max_age_seconds,
        )
        log.warning("Is TelegramBridgeEA attached and running on a chart? Folder: %s", bridge_dir)
        for p in stale:
            log.warning("  stuck: %s", p.name)
        log.warning("=" * 70)
