"""Unit-tests the new fill-screenshot pickup and daily pips/profit summary
in mt5_executor.py, using the same fake-MetaTrader5-module pattern as
test_average_breakeven.py (no real MT5 connection needed)."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign_store import Campaign, CampaignStore  # noqa: E402
from config import Config  # noqa: E402
from mt5_executor import Mt5Executor  # noqa: E402


@dataclass
class FakePosition:
    ticket: int
    magic: int
    price_open: float
    volume: float
    tp: float
    sl: float
    type: int = 0  # POSITION_TYPE_BUY by default


@dataclass
class FakeDeal:
    position_id: int
    magic: int
    symbol: str
    entry: int
    type: int
    price: float
    volume: float
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0


@dataclass
class FakeMt5:
    positions: list = field(default_factory=list)
    deals: list = field(default_factory=list)
    commondata_path: str = ""

    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def positions_get(self, ticket=None, symbol=None):
        if ticket is not None:
            return [p for p in self.positions if p.ticket == ticket]
        return list(self.positions)

    def terminal_info(self):
        return SimpleNamespace(commondata_path=self.commondata_path)

    def history_deals_get(self, date_from=None, date_to=None, position=None):
        if position is not None:
            return [d for d in self.deals if d.position_id == position]
        return list(self.deals)


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
        notify_enabled=True, telegram_notify_chat="me", daily_summary_time="23:55",
        dry_run=False,
    )
    base.update(overrides)
    return Config(**base)


def _executor_with(fake_mt5: FakeMt5) -> Mt5Executor:
    executor = Mt5Executor(_config())
    executor._mt5 = fake_mt5
    return executor


def test_take_pending_fill_notifications_pairs_png_and_metadata(tmp_path):
    fake = FakeMt5(commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    fills_dir = executor._bridge_dir() / "fills"
    fills_dir.mkdir(parents=True, exist_ok=True)
    (fills_dir / "555.png").write_bytes(b"fake-png-bytes")
    (fills_dir / "555.txt").write_text("DEAL=555\nPOSITION=123\nMAGIC=990000\nSYMBOL=XAUUSD\n")

    results = executor.take_pending_fill_notifications()

    assert len(results) == 1
    assert results[0].png_path.name == "555.png"
    assert results[0].meta == {"DEAL": "555", "POSITION": "123", "MAGIC": "990000", "SYMBOL": "XAUUSD"}
    # metadata file is consumed so it isn't picked up again on the next poll
    assert not (fills_dir / "555.txt").exists()


def test_take_pending_fill_notifications_leaves_metadata_without_screenshot_yet(tmp_path):
    # The EA writes the .png before the .txt - a .txt with no matching .png
    # means the EA hasn't finished writing this fill yet, not that there
    # never will be one - must be left alone for the next poll, not lost.
    fake = FakeMt5(commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    fills_dir = executor._bridge_dir() / "fills"
    fills_dir.mkdir(parents=True, exist_ok=True)
    (fills_dir / "777.txt").write_text("DEAL=777\nPOSITION=1\nMAGIC=990000\nSYMBOL=XAUUSD\n")

    results = executor.take_pending_fill_notifications()

    assert results == []
    assert (fills_dir / "777.txt").exists()


def test_position_details_reports_buy_position(tmp_path):
    positions = [FakePosition(ticket=42, magic=990000, price_open=4420.0, volume=0.03, tp=4426.0, sl=4414.0, type=0)]
    fake = FakeMt5(positions=positions, commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    details = executor.position_details(42)

    assert details.direction == "BUY"
    assert details.entry == 4420.0
    assert details.sl == 4414.0
    assert details.tp == 4426.0
    assert details.volume == 0.03


def test_position_details_returns_none_when_ticket_not_found(tmp_path):
    fake = FakeMt5(positions=[], commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    assert executor.position_details(999) is None


def test_daily_stats_counts_opens_and_computes_pips_and_profit_for_closed_buy(tmp_path):
    deals = [
        # position 1: filled AND closed today - a full round trip
        FakeDeal(position_id=1, magic=990000, symbol="XAUUSD", entry=0, type=0, price=4420.0, volume=0.01),
        FakeDeal(position_id=1, magic=990000, symbol="XAUUSD", entry=1, type=0, price=4426.0, volume=0.01, profit=6.0),
        # position 2: filled today, still open - counts as an opened entry only
        FakeDeal(position_id=2, magic=990001, symbol="XAUUSD", entry=0, type=0, price=4419.0, volume=0.01),
    ]
    fake = FakeMt5(deals=deals, commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    stats = executor.daily_stats(990000, 0.1, datetime(2026, 1, 1), datetime(2026, 1, 1, 23, 59))

    assert stats.opened_count == 2
    assert stats.opened_lots == 0.02
    assert stats.closed_count == 1
    assert stats.total_pips == 60.0  # (4426.0 - 4420.0) / 0.1
    assert stats.total_profit == 6.0


def test_daily_stats_sell_direction_mirrors_pips(tmp_path):
    deals = [
        FakeDeal(position_id=1, magic=990000, symbol="XAUUSD", entry=0, type=1, price=4430.0, volume=0.01),
        FakeDeal(position_id=1, magic=990000, symbol="XAUUSD", entry=1, type=1, price=4424.0, volume=0.01, profit=6.0),
    ]
    fake = FakeMt5(deals=deals, commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    stats = executor.daily_stats(990000, 0.1, datetime(2026, 1, 1), datetime(2026, 1, 1, 23, 59))

    assert stats.total_pips == 60.0  # (4430.0 - 4424.0) / 0.1, SELL mirrors direction


def test_daily_stats_ignores_deals_below_magic_base_or_other_symbol(tmp_path):
    deals = [
        FakeDeal(position_id=1, magic=100, symbol="XAUUSD", entry=0, type=0, price=4420.0, volume=0.01),
        FakeDeal(position_id=2, magic=990000, symbol="EURUSD", entry=0, type=0, price=1.1, volume=0.01),
    ]
    fake = FakeMt5(deals=deals, commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    stats = executor.daily_stats(990000, 0.1, datetime(2026, 1, 1), datetime(2026, 1, 1, 23, 59))

    assert stats.opened_count == 0
    assert stats.closed_count == 0


def test_campaign_store_find_by_magic(tmp_path):
    store = CampaignStore(path=tmp_path / "campaigns.json")
    store.add(Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000))
    store.add(Campaign(id="c2", symbol="XAUUSD", direction="SELL", magic=990001))

    assert store.find_by_magic(990001).id == "c2"
    assert store.find_by_magic(123456) is None
