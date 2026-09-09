"""Backtests THIS bot's own settings (.env) against the Telegram channel's
actual signal history and MT5's own historical M1 price bars for the
configured SYMBOL. Read-only and offline: no orders are placed, nothing is
written back to MT5/Telegram - only fetches (Telegram message history,
MT5 copy_rates_range) are made.

Must run on Windows next to a running, logged-in MT5 terminal (same
requirement as main.py's live mode) - needs the real MetaTrader5 package
and a real price history, so it cannot run in a sandboxed/CI environment.
See backtester.py's module docstring for the approximations this makes
(bar-based fills, SL-before-TP tie-break in an ambiguous bar, etc.) - read
those before trusting the numbers as more precise than they are.

Usage:
    python backtest.py                      # every ZONE signal in the channel's history
    python backtest.py --since 2026-06-01    # only signals from this date onward (UTC)
    python backtest.py --csv results.csv     # also write a per-order CSV report
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from datetime import datetime, timezone

from backtester import Bar, CampaignResult, simulate_campaign
from config import load_config
from signal_parser import SignalType, parse

log = logging.getLogger("backtest")


async def fetch_signal_history(config, since: datetime | None):
    from telegram_listener import build_client, resolve_chat_identifier

    client = build_client(config)
    await client.start()
    channel = resolve_chat_identifier(config.telegram_channel)

    signals = []
    total = 0
    async for message in client.iter_messages(channel, reverse=True):
        total += 1
        if since is not None and message.date < since:
            continue
        text = message.raw_text or ""
        if not text.strip():
            continue
        msg = parse(text)
        if msg.type == SignalType.ZONE:
            signals.append((message.date.timestamp(), msg.zone))

    await client.disconnect()
    log.info("scanned %d channel message(s), found %d ZONE signal(s)", total, len(signals))
    return signals


def fetch_price_bars(config, date_from: datetime, date_to: datetime):
    import MetaTrader5 as mt5  # noqa: N814 - package name

    kwargs = {}
    if config.mt5_path:
        kwargs["path"] = config.mt5_path
    if config.mt5_login:
        kwargs["login"] = config.mt5_login
        kwargs["password"] = config.mt5_password
        kwargs["server"] = config.mt5_server
    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
    if not mt5.symbol_select(config.symbol, True):
        raise RuntimeError(f"could not select symbol {config.symbol}")

    rates = mt5.copy_rates_range(config.symbol, mt5.TIMEFRAME_M1, date_from, date_to)
    if rates is None or len(rates) == 0:
        mt5.shutdown()
        raise RuntimeError(
            f"MT5 returned no M1 history for {config.symbol} between {date_from} and {date_to} - "
            "your broker may not keep price history that far back for this symbol/timeframe."
        )
    contract_size = mt5.symbol_info(config.symbol).trade_contract_size
    bars = [
        Bar(time=float(r["time"]), open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]))
        for r in rates
    ]
    mt5.shutdown()
    log.info("fetched %d M1 bar(s) for %s from %s to %s", len(bars), config.symbol, date_from, date_to)
    return bars, contract_size


def _print_report(results: list[CampaignResult]) -> None:
    total_pips = 0.0
    total_profit = 0.0
    total_filled = 0
    total_closed = 0
    total_orders = 0
    still_open = 0

    for r in results:
        ts = datetime.fromtimestamp(r.signal_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        log.info(
            "%s %s %.2f-%.2f: %d/%d filled, %d closed, %+.1f pips (%+.2f)",
            ts, r.direction, r.zone_low, r.zone_high, r.filled_count, len(r.orders),
            r.closed_count, r.total_pips, r.total_profit,
        )
        total_pips += r.total_pips
        total_profit += r.total_profit
        total_filled += r.filled_count
        total_closed += r.closed_count
        total_orders += len(r.orders)
        still_open += sum(1 for o in r.orders if o.filled and not o.closed)

    wins = sum(1 for r in results for o in r.orders if o.closed and o.pips > 0)
    log.info("=" * 70)
    log.info(
        "BACKTEST SUMMARY: %d signal(s), %d/%d orders filled, %d closed (%d still open at cutoff)",
        len(results), total_filled, total_orders, total_closed, still_open,
    )
    if total_closed:
        log.info("Win rate (closed orders): %d/%d (%.0f%%)", wins, total_closed, 100 * wins / total_closed)
    log.info("Total: %+.1f pips, %+.2f", total_pips, total_profit)
    log.info("=" * 70)


def _write_csv(results: list[CampaignResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "signal_time", "direction", "zone_low", "zone_high", "entry", "lot",
            "filled", "fill_time", "closed", "close_time", "close_price", "close_reason", "pips", "profit",
        ])
        for r in results:
            ts = datetime.fromtimestamp(r.signal_time, tz=timezone.utc).isoformat()
            for o in r.orders:
                writer.writerow([
                    ts, o.direction, r.zone_low, r.zone_high, o.entry_price, o.lot,
                    o.filled, o.fill_time, o.closed, o.close_time, o.close_price, o.close_reason, o.pips, o.profit,
                ])
    log.info("wrote per-order CSV report to %s", path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="YYYY-MM-DD (UTC) - only signals from this date onward; default: all channel history")
    parser.add_argument("--csv", help="also write a per-order CSV report to this path")
    args = parser.parse_args()

    config = load_config()
    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.since else None

    signals = asyncio.run(fetch_signal_history(config, since))
    if not signals:
        log.warning("no ZONE signals found in the requested range - nothing to backtest")
        return

    date_from = datetime.fromtimestamp(signals[0][0], tz=timezone.utc)
    date_to = datetime.now(tz=timezone.utc)
    bars, contract_size = fetch_price_bars(config, date_from, date_to)

    results = [simulate_campaign(signal_time, zone, bars, config, contract_size) for signal_time, zone in signals]

    _print_report(results)
    if args.csv:
        _write_csv(results, args.csv)


if __name__ == "__main__":
    main()
