"""Unit-tests backtester.simulate_campaign with synthetic M1 bars - no MT5
or Telegram needed (see backtester.py's module docstring for the
approximations this makes)."""
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtester import Bar, simulate_campaign  # noqa: E402
from config import Config  # noqa: E402
from signal_parser import ZoneSignal  # noqa: E402

CONTRACT_SIZE = 100.0


def _config(**overrides) -> Config:
    base = dict(
        telegram_api_id=0, telegram_api_hash="", telegram_session_name="x", telegram_channel="",
        mt5_path="", mt5_login=0, mt5_password="", mt5_server="", bridge_subfolder="tg_bridge",
        symbol="XAUUSD", lot_size=0.01, lot_tier_orders=3, lot_scaling_mode="additive", lot_multiplier=1.2,
        zone_step=0.5, zone_extend_front=0.0, zone_extend_back=0.0, pip_size=0.1,
        start_tp_pips=60, tp_increment_pips=10, tp_mode="ladder", tp_risk_reward_ratio=1.0,
        exit_mode="tp", trailing_stop_pips=36.0, trailing_stop_lock_pips=0.0,
        deviation_points=20, magic_base=990000,
        max_zone_width=20.0, risk_reward_trigger=1.0, monitor_interval_seconds=5,
        notify_enabled=False, telegram_notify_chat="me", daily_summary_time="23:55",
        dry_run=True,
    )
    base.update(overrides)
    return Config(**base)


def _bar(t, o, h, l, c) -> Bar:
    return Bar(time=float(t), open=o, high=h, low=l, close=c)


def test_order_never_fills_if_price_never_reaches_entry(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    bars = [_bar(100, 4430.0, 4431.0, 4429.0, 4430.0)]  # never dips down to 4420

    result = simulate_campaign(0.0, zone, bars, _config(), CONTRACT_SIZE)

    assert result.filled_count == 0
    assert result.closed_count == 0


def test_order_fills_when_bar_range_crosses_entry_then_hits_tp(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    config = _config(tp_mode="ladder", start_tp_pips=60, tp_increment_pips=0)  # TP = entry + 6.0
    bars = [
        _bar(100, 4422.0, 4422.5, 4419.5, 4420.0),  # crosses entry 4420.0 -> fills
        _bar(160, 4420.0, 4426.5, 4419.8, 4426.0),  # high reaches TP 4426.0
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    assert result.filled_count == 1
    order = result.orders[0]
    assert order.fill_time == 100.0
    assert order.closed is True
    assert order.close_reason == "tp"
    assert order.close_price == 4426.0
    assert order.pips == 60.0  # (4426.0 - 4420.0) / 0.1


def test_order_hits_sl_instead_of_tp_when_price_drops(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    config = _config(tp_mode="ladder", start_tp_pips=60, tp_increment_pips=0)  # SL = 4414.0
    bars = [
        _bar(100, 4420.0, 4420.5, 4419.5, 4420.0),  # fills
        _bar(160, 4420.0, 4420.2, 4413.5, 4414.0),  # low reaches SL 4414.0
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    order = result.orders[0]
    assert order.closed is True
    assert order.close_reason == "sl"
    assert order.close_price == 4414.0
    assert order.pips == -60.0


def test_sl_wins_tie_break_when_both_hit_in_same_bar(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    config = _config(tp_mode="ladder", start_tp_pips=60, tp_increment_pips=0)
    bars = [
        _bar(100, 4420.0, 4420.5, 4419.5, 4420.0),  # fills
        _bar(160, 4420.0, 4427.0, 4413.0, 4420.0),  # both SL (4414) and TP (4426) inside this bar's range
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    order = result.orders[0]
    assert order.close_reason == "sl"
    assert order.close_price == 4414.0


def test_order_still_open_at_cutoff_is_not_closed(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    bars = [_bar(100, 4420.0, 4420.5, 4419.5, 4420.0)]  # fills, no further bars

    result = simulate_campaign(0.0, zone, bars, _config(), CONTRACT_SIZE)

    order = result.orders[0]
    assert order.filled is True
    assert order.closed is False
    assert result.total_pips == 0.0  # unclosed orders don't count toward totals


def test_bars_before_signal_time_are_ignored(tmp_path):
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    bars = [
        _bar(50, 4420.0, 4420.5, 4419.5, 4420.0),  # before signal_time - must be ignored
        _bar(200, 4430.0, 4431.0, 4429.0, 4430.0),  # after signal_time, never touches entry
    ]

    result = simulate_campaign(100.0, zone, bars, _config(), CONTRACT_SIZE)

    assert result.filled_count == 0


def test_breakeven_moves_sl_to_avg_entry_once_1to1_reached_tp_mode(tmp_path):
    # Single order so avg entry == its own entry (4420.0); shared SL 4414.0
    # (risk = 6.0). Once bar close reaches 1:1 (4426.0), SL should move to
    # breakeven (4420.0) - a later dip to 4420.0 (not the original 4414.0)
    # should then close it at breakeven, not ride out to the original SL.
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    config = _config(tp_mode="ladder", start_tp_pips=1000, tp_increment_pips=0, risk_reward_trigger=1.0)
    bars = [
        _bar(100, 4420.0, 4420.5, 4419.5, 4420.0),  # fills
        _bar(160, 4420.0, 4426.5, 4420.0, 4426.0),  # profit reaches 1:1 -> SL moves to BE (4420.0)
        _bar(220, 4426.0, 4426.2, 4419.8, 4420.0),  # dips back to breakeven -> closes there
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    order = result.orders[0]
    assert order.moved_to_breakeven is True
    assert order.closed is True
    assert order.close_reason == "breakeven"
    assert order.close_price == 4420.0
    assert order.pips == 0.0


def test_trailing_stop_steps_and_closes_at_a_later_step(tmp_path):
    # EXIT_MODE=trailing_stop, 36 pips ($3.6) steps. Price runs to 72 pips
    # profit (two steps -> SL at entry+36pips=4423.6), then drops back to
    # that level and should close there, not at the original zone SL.
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4420.0, sl_pips=60)
    config = _config(exit_mode="trailing_stop", trailing_stop_pips=36.0)
    bars = [
        _bar(100, 4420.0, 4420.5, 4419.5, 4420.0),  # fills
        _bar(160, 4420.0, 4427.5, 4420.0, 4427.2),  # 72 pips profit -> SL steps to 4423.6
        _bar(220, 4427.2, 4427.4, 4423.5, 4423.6),  # drops back to 4423.6 -> closes there
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    order = result.orders[0]
    assert order.trailed is True
    assert order.closed is True
    assert order.close_reason == "trailing"
    assert order.close_price == 4423.6
    assert order.pips == 36.0


def test_sell_zone_mirrors_fill_and_exit_direction(tmp_path):
    zone = ZoneSignal(direction="SELL", zone_low=4430.0, zone_high=4430.0, sl_pips=60)
    config = _config(tp_mode="ladder", start_tp_pips=60, tp_increment_pips=0)  # SL=4436.0, TP=4424.0
    bars = [
        _bar(100, 4430.0, 4430.5, 4429.5, 4430.0),  # fills
        _bar(160, 4430.0, 4430.2, 4423.5, 4424.0),  # low reaches TP 4424.0
    ]

    result = simulate_campaign(0.0, zone, bars, config, CONTRACT_SIZE)

    order = result.orders[0]
    assert order.close_reason == "tp"
    assert order.close_price == 4424.0
    assert order.pips == 60.0
