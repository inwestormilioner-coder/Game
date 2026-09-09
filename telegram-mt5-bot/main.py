"""Wires Telegram -> signal parser -> order planner -> MT5 together.

Usage:
    python main.py                  # live: listens on Telegram, acts on MT5
    python main.py --replay FILE    # offline test: feed messages from a
                                     # text file (messages separated by a
                                     # line containing only "---"), no
                                     # Telegram/MT5 connection needed.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from campaign_store import Campaign, CampaignStore
from config import Config, load_config
from order_planner import plan_orders
from signal_parser import ParsedMessage, SignalType, parse

log = logging.getLogger("main")


class Bot:
    def __init__(self, config: Config, store: CampaignStore | None = None):
        self.config = config
        self.store = store or CampaignStore()
        self.executor = None
        self._last_trading_allowed: bool | None = None
        if not config.dry_run:
            from mt5_executor import Mt5Executor

            self.executor = Mt5Executor(config)
            self.executor.connect()

    async def handle_text(self, text: str) -> None:
        msg = parse(text)
        if msg.type == SignalType.ZONE:
            self._handle_zone(msg)
        elif msg.type == SignalType.BREAKEVEN:
            self._handle_breakeven(msg)
        elif msg.type == SignalType.CLOSE_ALL:
            self._handle_close_all(msg)
        elif msg.type == SignalType.PARTIAL_INFO:
            log.info("profit update (%s pips), no automated action taken", msg.profit_pips)
        else:
            log.info("unrecognized message, ignored: %s", text.replace("\n", " | "))

    def _handle_zone(self, msg: ParsedMessage) -> None:
        zone = msg.zone

        zone_width = zone.zone_high - zone.zone_low
        if zone_width > self.config.max_zone_width:
            log.error("=" * 70)
            log.error(
                "REFUSING zone signal: %.2f-%.2f is %.2f wide, over MAX_ZONE_WIDTH=%.2f - "
                "this looks like a parsing error, not a real signal. No orders placed.",
                zone.zone_low, zone.zone_high, zone_width, self.config.max_zone_width,
            )
            log.error("raw message: %s", msg.raw_text.replace("\n", " | "))
            log.error("=" * 70)
            return

        plans = plan_orders(
            zone,
            lot=self.config.lot_size,
            step=self.config.zone_step,
            pip_size=self.config.pip_size,
            start_tp_pips=self.config.start_tp_pips,
            tp_increment_pips=self.config.tp_increment_pips,
            lot_tier_orders=self.config.lot_tier_orders,
            lot_scaling_mode=self.config.lot_scaling_mode,
            lot_multiplier=self.config.lot_multiplier,
            tp_mode=self.config.tp_mode,
            tp_risk_reward_ratio=self.config.tp_risk_reward_ratio,
            exit_mode=self.config.exit_mode,
        )

        campaign = Campaign(
            id=uuid.uuid4().hex[:8],
            symbol=self.config.symbol,
            direction=zone.direction,
            magic=self.store.next_magic(self.config.magic_base),
            sl_pips=zone.sl_pips,
        )

        log.info(
            "ZONE signal: %s %s %.2f-%.2f SL=%.0fpips -> %d orders (campaign %s)",
            zone.direction, self.config.symbol, zone.zone_low, zone.zone_high, zone.sl_pips,
            len(plans), campaign.id,
        )

        if self.config.dry_run:
            for p in plans:
                if self.config.exit_mode == "trailing_stop":
                    log.info(
                        "  [DRY RUN] would place %s %.2f lots @ %.2f sl=%.2f no TP (trailing stop %.0f pips)",
                        p.direction, p.lot, p.entry_price, p.sl_price, self.config.trailing_stop_pips,
                    )
                else:
                    log.info(
                        "  [DRY RUN] would place %s %.2f lots @ %.2f sl=%.2f tp=%.2f (%.0f pips)",
                        p.direction, p.lot, p.entry_price, p.sl_price, p.tp_price, p.tp_pips,
                    )
            campaign.tickets = []
        else:
            campaign.tickets = self.executor.place_zone_orders(plans, campaign)

        self.store.add(campaign)

    def _handle_breakeven(self, msg: ParsedMessage) -> None:
        # Deliberately ignored: the channel's own "SL na BE" call is not
        # acted on. The bot manages SL itself - see monitor_campaigns() -
        # moving to the basket's average entry once profit reaches
        # RISK_REWARD_TRIGGER * risk (1:1 by default).
        log.info(
            "channel said 'SL na BE' (+%.0f pips) - ignoring, bot manages SL itself",
            msg.profit_pips or 0,
        )

    def _handle_close_all(self, msg: ParsedMessage) -> None:
        # Deliberately ignored too: the channel's "Zamykam calosc" call is
        # not acted on. Exits happen only from each order's own TP, or from
        # SL (initial, then moved to the basket average by monitor_campaigns
        # once 1:1 is reached) - never because the channel says so.
        log.info(
            "channel said 'Zamykam calosc' (+%.0f pips) - ignoring, bot only exits via TP/SL",
            msg.profit_pips or 0,
        )

    def _check_trading_allowed(self) -> None:
        """Logs once on each transition of what the Python API reports for
        MT5's "Algo Trading" toggle. Informational only: orders are placed
        by TelegramBridgeEA from inside the terminal (see mt5_executor.py),
        not via this API connection, and on at least one account this
        reading has been observed to say OFF even while manual trades and
        EAs traded fine - so treat this as a hint, not proof. The EA's own
        Eksperci/Experts log is the reliable source for whether it's
        actually placing orders."""
        allowed = self.executor.is_trading_allowed()
        if allowed != self._last_trading_allowed:
            if allowed:
                log.info("MT5 Algo Trading (as seen by the Python API) is ON.")
            else:
                log.info(
                    "MT5 Algo Trading (as seen by the Python API) is OFF - this may not be "
                    "accurate on this account/build; check the EA's own Eksperci log if orders "
                    "aren't appearing rather than relying on this line."
                )
            self._last_trading_allowed = allowed

    async def monitor_campaigns(self) -> None:
        """Own trade management, independent of the Telegram channel.

        EXIT_MODE=tp (default): moves SL to the basket average once profit
        reaches 1:1 (configurable) risk:reward.
        EXIT_MODE=trailing_stop: every open position's own SL continuously
        trails TRAILING_STOP_PIPS behind price instead - no basket-average
        move, since the two would fight each other.

        Either way, marks a campaign inactive once MT5 shows no pending
        orders or open positions left for it (all closed via TP/SL). No-op
        in DRY_RUN - there is no live MT5 position/price data to check
        without a real connection."""
        if self.config.dry_run or self.executor is None:
            log.info("DRY_RUN is on - trade monitoring loop is disabled")
            return

        while True:
            self._check_trading_allowed()
            self.executor.check_bridge_backlog()
            for campaign in self.store.most_recent_active(self.config.symbol):
                try:
                    if self.config.exit_mode == "trailing_stop":
                        self.executor.check_trailing_stops(
                            campaign, self.config.trailing_stop_pips, self.config.pip_size
                        )
                    else:
                        applied = self.executor.check_average_breakeven(campaign, self.config.risk_reward_trigger)
                        if applied:
                            self.store.mark_breakeven_applied(campaign.id)
                    if not self.executor.campaign_has_open_trades(campaign):
                        self.store.deactivate(campaign.id)
                except Exception:
                    log.exception("error monitoring campaign %s", campaign.id)
            await asyncio.sleep(self.config.monitor_interval_seconds)


def replay(config: Config, path: str) -> None:
    bot = Bot(config)
    text = open(path, encoding="utf-8").read()
    messages = [m.strip() for m in text.split("\n---\n") if m.strip()]
    for m in messages:
        asyncio.run(bot.handle_text(m))


async def live(config: Config) -> None:
    from telegram_listener import run_listener

    bot = Bot(config)
    await asyncio.gather(
        run_listener(config, bot.handle_text),
        bot.monitor_campaigns(),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", help="path to a text file of sample messages to replay offline")
    args = parser.parse_args()

    config = load_config()
    if config.dry_run:
        log.warning("DRY_RUN is ON - no real MT5 orders will be sent")

    if args.replay:
        replay(config, args.replay)
    else:
        asyncio.run(live(config))


if __name__ == "__main__":
    main()
