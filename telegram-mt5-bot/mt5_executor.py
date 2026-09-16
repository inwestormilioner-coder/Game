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

Four command types get written: OPEN_ORDERS and MODIFY_SL (one shared new
SL for every position matching a magic number - EXIT_MODE=tp's basket
breakeven), MODIFY_POSITIONS (a distinct new SL per ticket -
EXIT_MODE=trailing_stop's per-position trailing) and CANCEL_PENDING (every
still-pending order for a magic - trim_grid_if_half_filled below).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from campaign_store import Campaign
from config import Config
from order_planner import OrderPlan

log = logging.getLogger("mt5_executor")


@dataclass
class FillNotification:
    """One pending order that TelegramBridgeEA reports as filled - a chart
    screenshot taken at the moment of the fill, plus the handful of fields
    from its metadata file (see take_pending_fill_notifications)."""
    png_path: Path
    meta: dict


@dataclass
class PositionDetails:
    direction: str
    entry: float
    sl: float
    tp: float
    volume: float


@dataclass
class DailyStats:
    opened_count: int
    opened_lots: float
    closed_count: int
    total_pips: float
    total_profit: float


class Mt5Executor:
    def __init__(self, config: Config):
        self.config = config
        self._mt5 = None
        # manual-SL-sync state (see sync_manual_sl): last SL observed per
        # ticket, grouped by campaign magic, and the last SL THIS bot itself
        # commanded per ticket (breakeven/trailing) - the latter is what
        # lets sync_manual_sl tell "I moved this" from "the user moved this"
        # without mistaking its own not-yet-applied commands for a manual edit.
        self._last_known_sl: dict[int, dict[int, float]] = {}
        self._last_commanded_sl: dict[int, float] = {}

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
        a chart with FILE_COMMON file access - looks for command files.
        The subfolder name is configurable (MT5_BRIDGE_SUBFOLDER) so a
        second bot instance running against a second MT5 account doesn't
        cross-talk with the first - each needs its own EA instance with a
        matching BridgeSubfolder input."""
        info = self._mt5.terminal_info()
        bridge_dir = Path(info.commondata_path) / "Files" / self.config.bridge_subfolder
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
        for p in positions:
            self._last_commanded_sl[p.ticket] = avg_entry
        return True

    def sync_manual_sl(self, campaign: Campaign) -> None:
        """If you manually move the SL on ANY ONE open position of a
        campaign - dragging it on the chart, or editing it by hand in MT5's
        own Trade tab - this propagates that exact SL to every OTHER open
        position in the same campaign (pending, not-yet-filled orders are
        left alone; they get their own SL only once filled, from the zone's
        normal shared SL). Works the same in both EXIT_MODE settings.

        "Manual" is anything that changed since last tick AND doesn't match
        what THIS bot itself last commanded for that ticket (tracked in
        _last_commanded_sl by check_average_breakeven/check_trailing_stops)
        - without that check, a position picking up the bot's own queued
        breakeven/trailing SL one tick later than its siblings would look
        like a manual edit and trigger a pointless re-sync loop.

        Call this BEFORE check_average_breakeven/check_trailing_stops each
        poll tick: both of those only ever tighten a SL, never loosen one,
        so afterward they simply keep tightening from whatever level was
        just set here - no special-casing needed to keep them "working
        normally" after a manual sync.
        """
        mt5 = self._mt5
        positions = [p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic]
        last_known = self._last_known_sl.get(campaign.magic, {})

        manual_target = None
        if len(positions) >= 2:
            for pos in positions:
                prev_sl = last_known.get(pos.ticket)
                if prev_sl is None:
                    continue
                if pos.sl != prev_sl and pos.sl != self._last_commanded_sl.get(pos.ticket):
                    manual_target = pos.sl
                    break

        if manual_target is not None:
            updates = [(p.ticket, manual_target, p.tp) for p in positions if p.sl != manual_target]
            if updates:
                lines = ["TYPE=MODIFY_POSITIONS", f"SYMBOL={self.config.symbol}"]
                for ticket, sl, tp in updates:
                    lines.append(f"POSITION={ticket},{sl},{tp}")
                path = self._write_command(f"slsync_{campaign.id}", lines)
                log.info(
                    "manual SL change detected in campaign %s -> syncing whole basket to %.2f (%s)",
                    campaign.id, manual_target, path.name,
                )
                for ticket, sl, _ in updates:
                    self._last_commanded_sl[ticket] = sl

        self._last_known_sl[campaign.magic] = {p.ticket: p.sl for p in positions}

    def check_trailing_stops(
        self,
        campaign: Campaign,
        trailing_pips: float,
        pip_size: float,
        trailing_lock_pips: float = 0.0,
        trailing_basket: bool = False,
    ) -> bool:
        """EXIT_MODE=trailing_stop only: a STEPPED trailing stop - it does
        NOT continuously follow the price trailing_pips behind it.

        Two modes:
          - Per-position (trailing_basket=False, default): each open
            position trails independently, based on ITS OWN entry price.
          - Basket (trailing_basket=True): every open position in the
            campaign trails TOGETHER off the whole basket's own volume-
            weighted average entry price instead - once the basket's
            combined profit crosses trailing_pips, every position gets
            pulled toward the SAME candidate SL (each only actually
            queued for a MODIFY if that's tighter than its own current
            SL). Mirrors check_average_breakeven's avg_entry, but as
            continuous stepped trailing instead of a one-time move -
            useful when a campaign has many small entries that
            individually struggle to reach their own trailing threshold;
            in basket mode they ride along with the combined result.

        Either way, the stepping itself works the same, measured from
        whichever reference price (each position's own entry, or the
        basket average) applies:

          - Below trailing_pips profit: untouched, SL stays wherever it
            already is (the zone's shared initial SL) - not yet activated.
          - At trailing_pips profit: SL jumps to trailing_lock_pips profit
            (the reference price + trailing_lock_pips, or exactly
            breakeven when trailing_lock_pips=0, the default) - trailing
            "activates".
          - Every further trailing_pips of profit beyond that: SL jumps
            another trailing_pips in the profit direction, keeping the same
            trailing_lock_pips buffer on top each time. So right after each
            jump the gap between SL and the current price is exactly
            trailing_pips - trailing_lock_pips (it then widens as price
            keeps moving, until the next jump snaps it back) - it moves in
            discrete steps, not tick-by-tick with the price.

        trailing_lock_pips defaults to 0 (jumps land on exact breakeven /
        each previous trailing_pips-sized checkpoint, the original
        behavior). Set it e.g. to 12 so every jump - including the very
        first one - always leaves at least 12 pips of profit locked in
        instead of exact breakeven.

        Comparing each candidate against the position's own current live
        SL (not recomputing from scratch) is what makes this tightening-only
        for free: a price pullback computes a candidate from an
        already-passed, lower step, which is never better than the SL a
        later step already set - so this is safe to call every poll tick
        unconditionally, and SL never moves back down.

        Since each position can need a different new SL, this queues one
        MODIFY_POSITIONS command (targeting each position by ticket) rather
        than the single-shared-SL MODIFY_SL command check_average_breakeven
        uses.

        Returns True the moment ANY update gets queued this call - main.py
        uses that to latch campaign.trailing_activated (see
        campaign_store.CampaignStore.mark_trailing_activated), which
        trim_grid_if_half_filled below then acts on. False otherwise
        (nothing to report, NOT "trailing turned off").
        """
        mt5 = self._mt5
        positions = [p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic]
        if not positions:
            return False

        bid, ask = self.current_price()
        trail_distance = trailing_pips * pip_size
        lock_distance = trailing_lock_pips * pip_size

        basket_reference_price = None
        if trailing_basket:
            total_volume = sum(p.volume for p in positions)
            if total_volume <= 0:
                return False
            basket_reference_price = sum(p.price_open * p.volume for p in positions) / total_volume

        updates = []
        for pos in positions:
            reference_price = basket_reference_price if trailing_basket else pos.price_open
            profit_distance = (bid - reference_price) if campaign.direction == "BUY" else (reference_price - ask)
            if profit_distance < trail_distance:
                continue
            # round() before floor() guards against float noise (e.g.
            # 3.5999999999999996) putting profit_distance one step short of
            # an exact multiple of trail_distance, which would delay the
            # next jump by one tick's worth of price.
            steps = math.floor(round(profit_distance / trail_distance, 6))
            locked_distance = (steps - 1) * trail_distance + lock_distance

            if campaign.direction == "BUY":
                candidate_sl = round(reference_price + locked_distance, 2)
                improved = candidate_sl > pos.sl
            else:
                candidate_sl = round(reference_price - locked_distance, 2)
                improved = candidate_sl < pos.sl
            if improved:
                updates.append((pos.ticket, candidate_sl, pos.tp))

        if not updates:
            return False

        lines = ["TYPE=MODIFY_POSITIONS", f"SYMBOL={self.config.symbol}"]
        for ticket, sl, tp in updates:
            lines.append(f"POSITION={ticket},{sl},{tp}")

        path = self._write_command(f"trail_{campaign.id}", lines)
        log.info(
            "queued trailing SL update for %d position(s) in campaign %s -> %s",
            len(updates), campaign.id, path.name,
        )
        for ticket, sl, tp in updates:
            self._last_commanded_sl[ticket] = sl
        return True

    def trim_grid_if_half_filled(self, campaign: Campaign) -> None:
        """Once trailing has activated for a campaign (campaign.trailing_
        activated, set by main.py from check_trailing_stops's return value)
        AND at least half of the zone's originally-planned orders have
        filled, cancels whatever pending orders are still left in that
        grid: trailing is already protecting the open positions' profit, so
        there's no reason to keep waiting for (and adding the risk of) the
        rest of the zone filling too.

        "Half filled" compares currently OPEN positions of this magic
        against campaign.total_orders (the count plan_orders() produced at
        signal time, stored on the campaign) - good enough since this is
        checked from early in a campaign's life, before anything from it
        has had a chance to close. campaign.total_orders==0 (an old
        campaign from before this field existed) makes this a no-op.

        Safe to call every poll tick unconditionally: once nothing is left
        pending, orders_get comes back empty and this is just a no-op read.
        """
        if not campaign.trailing_activated or campaign.total_orders <= 0:
            return

        mt5 = self._mt5
        open_count = len([p for p in (mt5.positions_get(symbol=self.config.symbol) or ()) if p.magic == campaign.magic])
        if open_count / campaign.total_orders < 0.5:
            return

        pending = [o for o in (mt5.orders_get(symbol=self.config.symbol) or ()) if o.magic == campaign.magic]
        if not pending:
            return

        lines = ["TYPE=CANCEL_PENDING", f"MAGIC={campaign.magic}", f"SYMBOL={self.config.symbol}"]
        path = self._write_command(f"trim_{campaign.id}", lines)
        log.info(
            "campaign %s: %d/%d orders filled (trailing already active) -> cancelling %d remaining pending order(s) -> %s",
            campaign.id, open_count, campaign.total_orders, len(pending), path.name,
        )

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

    def take_pending_fill_notifications(self) -> List[FillNotification]:
        """Picks up screenshot+metadata pairs TelegramBridgeEA drops into
        the bridge folder's fills\\ subfolder whenever one of our pending
        orders actually fills (see TelegramBridgeEA.mq5's
        OnTradeTransaction) - one chart screenshot taken at the moment of
        the fill, one plain-text metadata file (DEAL/POSITION/MAGIC/SYMBOL)
        with the same base name. The metadata file is only written AFTER
        the screenshot is copied in, so a .txt with no matching .png yet
        just means the EA is mid-write - left alone for the next poll."""
        fills_dir = self._bridge_dir() / "fills"
        fills_dir.mkdir(exist_ok=True)
        results = []
        for meta_path in sorted(fills_dir.glob("*.txt")):
            png_path = meta_path.with_suffix(".png")
            if not png_path.exists():
                continue
            meta = {}
            for line in meta_path.read_text(encoding="ascii").splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    meta[key] = value
            meta_path.unlink()
            results.append(FillNotification(png_path=png_path, meta=meta))
        return results

    def position_details(self, ticket: int) -> Optional[PositionDetails]:
        positions = self._mt5.positions_get(ticket=ticket)
        if not positions:
            return None
        p = positions[0]
        direction = "BUY" if p.type == self._mt5.POSITION_TYPE_BUY else "SELL"
        return PositionDetails(direction=direction, entry=p.price_open, sl=p.sl, tp=p.tp, volume=p.volume)

    def daily_stats(self, magic_base: int, pip_size: float, day_start: datetime, day_end: datetime) -> DailyStats:
        """Reads today's deal history (a read-only MT5 API call, always
        available regardless of the retcode-10027 restriction on order
        placement) to report what actually filled and closed today,
        independent of when a campaign's zone signal originally arrived.
        magic_base filters to this bot's own trades - campaign magics are
        assigned sequentially upward from it (campaign_store.next_magic)
        and never reused, so ">= magic_base" is a safe "is this ours" test.

        Pips for a closed position are computed from its own deal history
        (open price vs. volume-weighted close price), not from sl_pips,
        since a position can close at TP, at SL, or (once 1:1 is reached)
        at the basket-average SL - all different distances from entry.
        """
        mt5 = self._mt5
        deals = mt5.history_deals_get(day_start, day_end) or ()
        deals = [d for d in deals if d.symbol == self.config.symbol and d.magic >= magic_base]

        opened = [d for d in deals if d.entry == mt5.DEAL_ENTRY_IN]
        closed_out = [d for d in deals if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]

        total_profit = 0.0
        total_pips = 0.0
        seen_positions = set()
        for out_deal in closed_out:
            pid = out_deal.position_id
            if pid in seen_positions:
                continue
            seen_positions.add(pid)

            pos_deals = mt5.history_deals_get(position=pid) or ()
            in_deals = [d for d in pos_deals if d.entry == mt5.DEAL_ENTRY_IN]
            out_deals = [d for d in pos_deals if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]
            if not in_deals or not out_deals:
                continue

            in_price = in_deals[0].price
            out_volume = sum(d.volume for d in out_deals)
            out_price = sum(d.price * d.volume for d in out_deals) / out_volume
            direction = "BUY" if in_deals[0].type == mt5.DEAL_TYPE_BUY else "SELL"
            pips = (out_price - in_price) / pip_size if direction == "BUY" else (in_price - out_price) / pip_size

            total_pips += pips
            total_profit += sum(d.profit + d.swap + d.commission for d in out_deals)

        return DailyStats(
            opened_count=len(opened),
            opened_lots=round(sum(d.volume for d in opened), 2),
            closed_count=len(seen_positions),
            total_pips=round(total_pips, 1),
            total_profit=round(total_profit, 2),
        )
