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
    def __init__(self, config: Config):
        self.config = config
        self.store = CampaignStore()
        self.executor = None
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
        plans = plan_orders(
            zone,
            lot=self.config.lot_size,
            step=self.config.zone_step,
            pip_size=self.config.pip_size,
            start_tp_pips=self.config.start_tp_pips,
            tp_increment_pips=self.config.tp_increment_pips,
        )

        campaign = Campaign(
            id=uuid.uuid4().hex[:8],
            symbol=self.config.symbol,
            direction=zone.direction,
            magic=self.store.next_magic(self.config.magic_base),
        )

        log.info(
            "ZONE signal: %s %s %.2f-%.2f SL=%.0fpips -> %d orders (campaign %s)",
            zone.direction, self.config.symbol, zone.zone_low, zone.zone_high, zone.sl_pips,
            len(plans), campaign.id,
        )

        if self.config.dry_run:
            for p in plans:
                log.info(
                    "  [DRY RUN] would place %s %.2f lots @ %.2f sl=%.2f tp=%.2f (%.0f pips)",
                    p.direction, p.lot, p.entry_price, p.sl_price, p.tp_price, p.tp_pips,
                )
            campaign.tickets = []
        else:
            campaign.tickets = self.executor.place_zone_orders(plans, campaign)

        self.store.add(campaign)

    def _active_campaigns(self, msg: ParsedMessage) -> list[Campaign]:
        campaigns = self.store.most_recent_active(self.config.symbol)
        if not campaigns:
            log.warning("update message received but no active campaign is tracked: %s", msg.raw_text)
        return campaigns

    def _handle_breakeven(self, msg: ParsedMessage) -> None:
        for campaign in self._active_campaigns(msg):
            log.info("BREAKEVEN update (+%.0f pips) for campaign %s", msg.profit_pips or 0, campaign.id)
            if self.config.dry_run:
                log.info("  [DRY RUN] would move SL to entry for all open positions in campaign %s", campaign.id)
            else:
                self.executor.move_sl_to_breakeven(campaign)

    def _handle_close_all(self, msg: ParsedMessage) -> None:
        for campaign in self._active_campaigns(msg):
            log.info("CLOSE ALL update (+%.0f pips) for campaign %s", msg.profit_pips or 0, campaign.id)
            if self.config.dry_run:
                log.info("  [DRY RUN] would cancel pending orders and close open positions for campaign %s", campaign.id)
            else:
                self.executor.close_campaign(campaign)
            self.store.deactivate(campaign.id)


def replay(config: Config, path: str) -> None:
    bot = Bot(config)
    text = open(path, encoding="utf-8").read()
    messages = [m.strip() for m in text.split("\n---\n") if m.strip()]
    for m in messages:
        asyncio.run(bot.handle_text(m))


async def live(config: Config) -> None:
    from telegram_listener import run_listener

    bot = Bot(config)
    await run_listener(config, bot.handle_text)


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
