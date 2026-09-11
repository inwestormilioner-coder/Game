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
from datetime import datetime

from campaign_store import Campaign, CampaignStore
from config import Config, load_config
from order_planner import plan_orders
from signal_parser import ParsedMessage, SignalType, ZoneSignal, parse

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
            self._handle_zone(msg.zone, msg.raw_text)
        elif msg.type == SignalType.ADD_TO_ZONE:
            self._handle_add_to_zone(msg)
        elif msg.type == SignalType.BREAKEVEN:
            self._handle_breakeven(msg)
        elif msg.type == SignalType.CLOSE_ALL:
            self._handle_close_all(msg)
        elif msg.type == SignalType.PARTIAL_INFO:
            log.info("profit update (%s pips), no automated action taken", msg.profit_pips)
        else:
            log.info("unrecognized message, ignored: %s", text.replace("\n", " | "))

    def _handle_add_to_zone(self, msg: ParsedMessage) -> None:
        """Channel said "dolóz do pozycji" with a new zone/SL but no
        "Kierunek: Buy/Sell Gold" of its own - treated as another zone
        signal, with direction inferred from the most recently active
        campaign for this symbol (per the user's request: "kolejny sygnal,
        kierunek zgodny z poprzednim")."""
        campaigns = self.store.most_recent_active(self.config.symbol)
        if not campaigns:
            log.info(
                "channel said 'dolóz do pozycji' with a new zone, but there's no active campaign "
                "to infer a direction from - ignoring: %s", msg.raw_text.replace("\n", " | "),
            )
            return

        direction = campaigns[0].direction
        zone = ZoneSignal(
            direction=direction,
            zone_low=msg.add_to_zone.zone_low,
            zone_high=msg.add_to_zone.zone_high,
            sl_pips=msg.add_to_zone.sl_pips,
        )
        log.info(
            "channel said 'dolóz do pozycji' - treating as a new %s zone signal "
            "(direction inferred from the most recent active campaign)", direction,
        )
        self._handle_zone(zone, msg.raw_text)

    def _handle_zone(self, zone: ZoneSignal, raw_text: str = "") -> None:
        zone_width = zone.zone_high - zone.zone_low
        if zone_width > self.config.max_zone_width:
            log.error("=" * 70)
            log.error(
                "REFUSING zone signal: %.2f-%.2f is %.2f wide, over MAX_ZONE_WIDTH=%.2f - "
                "this looks like a parsing error, not a real signal. No orders placed.",
                zone.zone_low, zone.zone_high, zone_width, self.config.max_zone_width,
            )
            log.error("raw message: %s", raw_text.replace("\n", " | "))
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
            zone_extend_front=self.config.zone_extend_front,
            zone_extend_back=self.config.zone_extend_back,
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
                            campaign, self.config.trailing_stop_pips, self.config.pip_size,
                            self.config.trailing_stop_lock_pips,
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

    async def watch_fills(self, notifier) -> None:
        """Sends a chart screenshot + entry details to Telegram (see
        notifier.py) whenever TelegramBridgeEA reports one of our pending
        orders actually filled - not when it's merely placed. See
        mt5_executor.take_pending_fill_notifications and the EA's
        OnTradeTransaction. No-op without a live MT5 connection."""
        if self.executor is None:
            return
        while True:
            try:
                for fn in self.executor.take_pending_fill_notifications():
                    caption = self._format_fill_caption(fn.meta)
                    await notifier.send_photo(fn.png_path, caption)
                    fn.png_path.unlink(missing_ok=True)
            except Exception:
                log.exception("error sending fill notification")
            await asyncio.sleep(self.config.monitor_interval_seconds)

    def _format_fill_caption(self, meta: dict) -> str:
        magic = int(meta.get("MAGIC", 0))
        position_id = int(meta.get("POSITION", 0))
        symbol = meta.get("SYMBOL", self.config.symbol)
        campaign = self.store.find_by_magic(magic)
        details = self.executor.position_details(position_id)

        lines = [f"✅ Złapane entry - {symbol}"]
        if details:
            lines.append(f"{details.direction} {details.volume:.2f} lota @ {details.entry:.2f}")
            lines.append(f"SL: {details.sl:.2f}  TP: {details.tp:.2f}")
        if campaign:
            lines.append(f"Kampania: {campaign.id}")
        return "\n".join(lines)

    async def daily_summary_loop(self, notifier) -> None:
        """Sends one automatic summary per day at config.daily_summary_time
        (local time, "HH:MM") of what actually filled/closed that day - see
        mt5_executor.daily_stats. No-op without a live MT5 connection."""
        if self.executor is None:
            return
        try:
            target_h, target_m = (int(x) for x in self.config.daily_summary_time.split(":"))
        except ValueError:
            log.error(
                "DAILY_SUMMARY_TIME=%r is not HH:MM - daily summary disabled", self.config.daily_summary_time
            )
            return

        last_sent = None
        while True:
            now = datetime.now()
            if now.hour == target_h and now.minute == target_m and last_sent != now.date():
                try:
                    await self._send_daily_summary(notifier, now)
                    last_sent = now.date()
                except Exception:
                    log.exception("error sending daily summary")
            await asyncio.sleep(30)

    async def _send_daily_summary(self, notifier, now: datetime) -> None:
        day_start = datetime.combine(now.date(), datetime.min.time())
        day_end = datetime.combine(now.date(), datetime.max.time())
        stats = self.executor.daily_stats(self.config.magic_base, self.config.pip_size, day_start, day_end)
        text = (
            f"\U0001F4CA Podsumowanie dnia {now.date().isoformat()}\n"
            f"Złapane entry: {stats.opened_count} ({stats.opened_lots:.2f} lota)\n"
            f"Zamknięte pozycje: {stats.closed_count}\n"
            f"Wynik: {stats.total_pips:+.1f} pips ({stats.total_profit:+.2f})"
        )
        await notifier.send_text(text)


def replay(config: Config, path: str) -> None:
    bot = Bot(config)
    text = open(path, encoding="utf-8").read()
    messages = [m.strip() for m in text.split("\n---\n") if m.strip()]
    for m in messages:
        asyncio.run(bot.handle_text(m))


async def live(config: Config) -> None:
    from telegram_listener import build_client, run_listener

    client = build_client(config)
    await client.start()

    bot = Bot(config)
    tasks = [run_listener(client, config, bot.handle_text), bot.monitor_campaigns()]

    if config.notify_enabled and not config.dry_run:
        from notifier import Notifier, resolve_chat_identifier

        notifier = Notifier(client, resolve_chat_identifier(config.telegram_notify_chat))
        tasks.append(bot.watch_fills(notifier))
        tasks.append(bot.daily_summary_loop(notifier))
    elif config.notify_enabled:
        log.info("NOTIFY_ENABLED is on but DRY_RUN is on too - no MT5 connection, notifications stay off")

    await asyncio.gather(*tasks)


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
