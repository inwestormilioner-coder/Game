"""Unit-tests mt5_executor without a real MT5 connection, by injecting a
fake MetaTrader5-shaped module. Trade-modifying calls no longer go through
order_send() directly (see mt5_executor.py's module docstring) - they write
command files into a "Common\\Files\\tg_bridge" folder for TelegramBridgeEA
to pick up, so these tests check file contents instead of order_send()
calls for those paths."""
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign_store import Campaign  # noqa: E402
from config import Config  # noqa: E402
from mt5_executor import Mt5Executor  # noqa: E402
from order_planner import plan_orders  # noqa: E402
from signal_parser import ZoneSignal  # noqa: E402


@dataclass
class FakePosition:
    ticket: int
    magic: int
    price_open: float
    volume: float
    tp: float
    sl: float


@dataclass
class FakeOrder:
    ticket: int
    magic: int


@dataclass
class FakeMt5:
    positions: list
    bid: float
    ask: float
    commondata_path: str
    orders: list = field(default_factory=list)
    sent_requests: list = field(default_factory=list)
    trade_allowed: bool = True

    TRADE_ACTION_SLTP = "SLTP"
    TRADE_RETCODE_DONE = 10009

    def positions_get(self, symbol=None):
        return list(self.positions)

    def orders_get(self, symbol=None):
        return list(self.orders)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self.bid, ask=self.ask)

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=self.trade_allowed, commondata_path=self.commondata_path)

    def order_send(self, request):
        self.sent_requests.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=request.get("position"))


def _config(**overrides) -> Config:
    base = dict(
        telegram_api_id=0, telegram_api_hash="", telegram_session_name="x", telegram_channel="",
        mt5_path="", mt5_login=0, mt5_password="", mt5_server="", bridge_subfolder="tg_bridge",
        symbol="XAUUSD", lot_size=0.01, lot_tier_orders=3, lot_scaling_mode="additive", lot_multiplier=1.2,
        zone_step=0.5, zone_extend_front=0.0, zone_extend_back=0.0, pip_size=0.1,
        start_tp_pips=60, tp_increment_pips=10, tp_mode="ladder", tp_risk_reward_ratio=1.0,
        exit_mode="tp", trailing_stop_pips=36.0,
        deviation_points=20, magic_base=990000,
        max_zone_width=20.0, risk_reward_trigger=1.0, monitor_interval_seconds=5, dry_run=False,
    )
    base.update(overrides)
    return Config(**base)


def _executor_with(fake_mt5: FakeMt5) -> Mt5Executor:
    executor = Mt5Executor(_config())
    executor._mt5 = fake_mt5
    return executor


def _bridge_files(fake_mt5: FakeMt5, prefix: str = "") -> list[Path]:
    bridge_dir = Path(fake_mt5.commondata_path) / "Files" / "tg_bridge"
    if not bridge_dir.exists():
        return []
    return sorted(p for p in bridge_dir.glob("*.txt") if p.name.startswith(prefix))


def test_no_action_below_1to1(tmp_path):
    # BUY basket: shared SL 4414.0 (one price for the whole grid), avg
    # entry 4422.5 -> risk = 8.5, needs bid >= 4431.0 to trigger
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0, sl=4414.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4431.0, sl=4414.0),
    ]
    fake = FakeMt5(positions=positions, bid=4429.0, ask=4429.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is False
    assert fake.sent_requests == []
    assert _bridge_files(fake, "modify_") == []


def test_moves_sl_to_basket_average_once_1to1_reached(tmp_path):
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0, sl=4414.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4431.0, sl=4414.0),
    ]
    fake = FakeMt5(positions=positions, bid=4431.0, ask=4431.2, commondata_path=str(tmp_path))  # profit_price = 8.5 == risk
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is True
    assert fake.sent_requests == []  # no direct order_send() - queued for the EA instead

    files = _bridge_files(fake, "modify_")
    assert len(files) == 1
    content = files[0].read_text()
    assert "TYPE=MODIFY_SL" in content
    assert "MAGIC=990000" in content
    assert "SYMBOL=XAUUSD" in content
    assert "NEW_SL=4422.5" in content  # (4420 + 4425) / 2, NOT each position's own entry/SL


def test_skips_campaigns_already_marked_applied(tmp_path):
    fake = FakeMt5(positions=[], bid=5000.0, ask=5000.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60, breakeven_applied=True)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is False
    assert fake.sent_requests == []


def test_sell_basket_uses_ask_and_mirrors_math(tmp_path):
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4430.0, volume=0.01, tp=4424.0, sl=4436.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4419.0, sl=4436.0),
    ]
    # avg entry 4427.5, shared SL 4436.0 -> risk = 8.5, needs ask <= 4419.0
    fake = FakeMt5(positions=positions, bid=4418.8, ask=4419.0, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="SELL", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is True
    files = _bridge_files(fake, "modify_")
    assert len(files) == 1
    assert "NEW_SL=4427.5" in files[0].read_text()


def test_trailing_stop_tightens_sl_when_price_moves_favorably(tmp_path):
    # BUY position entry 4420, initial (shared-zone) SL 4414. Price has run
    # up to bid=4460 - trailing 36 pips (=$3.6) behind gives candidate SL
    # 4456.4, well past the current 4414, so it should update.
    positions = [FakePosition(ticket=111, magic=990000, price_open=4420.0, volume=0.01, tp=0.0, sl=4414.0)]
    fake = FakeMt5(positions=positions, bid=4460.0, ask=4460.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    executor.check_trailing_stops(campaign, trailing_pips=36, pip_size=0.1)

    files = _bridge_files(fake, "trail_")
    assert len(files) == 1
    content = files[0].read_text()
    assert "TYPE=MODIFY_POSITIONS" in content
    assert "POSITION=111,4456.4,0.0" in content


def test_trailing_stop_does_not_loosen_an_already_tighter_sl(tmp_path):
    # Candidate SL from the current price (4460 - 3.6 = 4456.4) is WORSE
    # than the position's current SL (4458.0, already trailed further by
    # an earlier tick) - must not move it backwards.
    positions = [FakePosition(ticket=111, magic=990000, price_open=4420.0, volume=0.01, tp=0.0, sl=4458.0)]
    fake = FakeMt5(positions=positions, bid=4460.0, ask=4460.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    executor.check_trailing_stops(campaign, trailing_pips=36, pip_size=0.1)

    assert _bridge_files(fake, "trail_") == []


def test_trailing_stop_sell_direction_trails_above_ask(tmp_path):
    positions = [FakePosition(ticket=222, magic=990000, price_open=4430.0, volume=0.01, tp=0.0, sl=4436.0)]
    fake = FakeMt5(positions=positions, bid=4389.8, ask=4390.0, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="SELL", magic=990000, sl_pips=60)

    executor.check_trailing_stops(campaign, trailing_pips=36, pip_size=0.1)

    files = _bridge_files(fake, "trail_")
    assert len(files) == 1
    # SELL: candidate = ask + trailing distance = 4390.0 + 3.6 = 4393.6
    assert "POSITION=222,4393.6,0.0" in files[0].read_text()


def test_trailing_stop_handles_each_position_independently(tmp_path):
    # Candidate SL from the current price is 4460.0 - 3.6 = 4456.4 for
    # both positions (same symbol/price), but only ticket 1's current SL
    # (4414.0) is behind that; ticket 2 (4457.0, already trailed tighter
    # than the new candidate by an earlier tick) must be left alone.
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=0.0, sl=4414.0),
        FakePosition(ticket=2, magic=990000, price_open=4455.0, volume=0.01, tp=0.0, sl=4457.0),
    ]
    fake = FakeMt5(positions=positions, bid=4460.0, ask=4460.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    executor.check_trailing_stops(campaign, trailing_pips=36, pip_size=0.1)

    files = _bridge_files(fake, "trail_")
    assert len(files) == 1
    content = files[0].read_text()
    assert "POSITION=1,4456.4,0.0" in content
    assert "POSITION=2" not in content


def test_place_zone_orders_writes_one_command_file(tmp_path):
    fake = FakeMt5(positions=[], bid=4419.0, ask=4419.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4421.0, sl_pips=60)
    plans = plan_orders(zone, lot=0.01, step=0.5, pip_size=0.1, start_tp_pips=60, tp_increment_pips=10)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    tickets = executor.place_zone_orders(plans, campaign)

    assert tickets == []
    assert fake.sent_requests == []  # no direct order_send() - queued for the EA instead

    files = _bridge_files(fake, "orders_")
    assert len(files) == 1
    content = files[0].read_text()
    assert "TYPE=OPEN_ORDERS" in content
    assert "MAGIC=990000" in content
    assert "SYMBOL=XAUUSD" in content
    assert "COMMENT=tg-c1" in content
    assert f"COUNT={len(plans)}" in content
    assert content.count("ORDER=") == len(plans)
    assert "ORDER=BUY,4420.0,4414.0,4426.0,0.01" in content


def test_check_bridge_backlog_warns_on_stale_files(tmp_path, caplog):
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    bridge_dir = executor._bridge_dir()
    stuck = bridge_dir / "orders_old_1.txt"
    stuck.write_text("TYPE=OPEN_ORDERS\n")
    old_time = time.time() - 120
    os.utime(stuck, (old_time, old_time))

    import logging
    with caplog.at_level(logging.WARNING):
        executor.check_bridge_backlog(max_age_seconds=30)

    assert any("unprocessed" in r.message for r in caplog.records)


def test_check_bridge_backlog_silent_when_nothing_stale(tmp_path, caplog):
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, commondata_path=str(tmp_path))
    executor = _executor_with(fake)

    import logging
    with caplog.at_level(logging.WARNING):
        executor.check_bridge_backlog(max_age_seconds=30)

    assert caplog.records == []


def test_campaign_has_open_trades_true_with_pending_orders(tmp_path):
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, orders=[FakeOrder(ticket=1, magic=990000)], commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is True


def test_campaign_has_open_trades_true_with_open_positions(tmp_path):
    positions = [FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0, sl=4414.0)]
    fake = FakeMt5(positions=positions, bid=4420.0, ask=4420.2, orders=[], commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is True


def test_campaign_has_open_trades_false_once_everything_closed(tmp_path):
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, orders=[], commondata_path=str(tmp_path))
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is False


def test_is_trading_allowed_reflects_terminal_state(tmp_path):
    allowed = FakeMt5(positions=[], bid=4420.0, ask=4420.2, trade_allowed=True, commondata_path=str(tmp_path))
    disabled = FakeMt5(positions=[], bid=4420.0, ask=4420.2, trade_allowed=False, commondata_path=str(tmp_path))

    assert _executor_with(allowed).is_trading_allowed() is True
    assert _executor_with(disabled).is_trading_allowed() is False


def test_campaign_has_open_trades_ignores_other_campaigns_magic(tmp_path):
    fake = FakeMt5(
        positions=[FakePosition(ticket=1, magic=111111, price_open=4420.0, volume=0.01, tp=4426.0, sl=4414.0)],
        bid=4420.0, ask=4420.2,
        orders=[FakeOrder(ticket=2, magic=222222)],
        commondata_path=str(tmp_path),
    )
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is False
