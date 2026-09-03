"""Unit-tests the average-entry breakeven math in mt5_executor without a
real MT5 connection, by injecting a fake MetaTrader5-shaped module."""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign_store import Campaign  # noqa: E402
from config import Config  # noqa: E402
from mt5_executor import Mt5Executor  # noqa: E402


@dataclass
class FakePosition:
    ticket: int
    magic: int
    price_open: float
    volume: float
    tp: float


@dataclass
class FakeOrder:
    ticket: int
    magic: int


@dataclass
class FakeMt5:
    positions: list
    bid: float
    ask: float
    orders: list = field(default_factory=list)
    sent_requests: list = field(default_factory=list)

    TRADE_ACTION_SLTP = "SLTP"
    TRADE_RETCODE_DONE = 10009

    def positions_get(self, symbol=None):
        return list(self.positions)

    def orders_get(self, symbol=None):
        return list(self.orders)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self.bid, ask=self.ask)

    def order_send(self, request):
        self.sent_requests.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=request.get("position"))


def _config(**overrides) -> Config:
    base = dict(
        telegram_api_id=0, telegram_api_hash="", telegram_session_name="x", telegram_channel="",
        mt5_path="", mt5_login=0, mt5_password="", mt5_server="",
        symbol="XAUUSD", lot_size=0.01, zone_step=0.5, pip_size=0.1,
        start_tp_pips=60, tp_increment_pips=10, deviation_points=20, magic_base=990000,
        risk_reward_trigger=1.0, monitor_interval_seconds=5, dry_run=False,
    )
    base.update(overrides)
    return Config(**base)


def _executor_with(fake_mt5: FakeMt5) -> Mt5Executor:
    executor = Mt5Executor(_config())
    executor._mt5 = fake_mt5
    return executor


def test_no_action_below_1to1():
    # BUY basket: avg entry 4422.5, risk = 60 pips * 0.1 = $6 -> needs bid >= 4428.5
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4431.0),
    ]
    fake = FakeMt5(positions=positions, bid=4427.0, ask=4427.2)  # profit_price = 4.5 < 6
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is False
    assert fake.sent_requests == []


def test_moves_sl_to_basket_average_once_1to1_reached():
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4431.0),
    ]
    fake = FakeMt5(positions=positions, bid=4428.5, ask=4428.7)  # profit_price = 6.0 == risk
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is True
    assert len(fake.sent_requests) == 2
    for req in fake.sent_requests:
        assert req["sl"] == 4422.5  # (4420 + 4425) / 2, NOT each position's own entry
    assert {req["position"] for req in fake.sent_requests} == {1, 2}


def test_skips_campaigns_already_marked_applied():
    fake = FakeMt5(positions=[], bid=5000.0, ask=5000.2)
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60, breakeven_applied=True)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is False
    assert fake.sent_requests == []


def test_sell_basket_uses_ask_and_mirrors_math():
    positions = [
        FakePosition(ticket=1, magic=990000, price_open=4430.0, volume=0.01, tp=4424.0),
        FakePosition(ticket=2, magic=990000, price_open=4425.0, volume=0.01, tp=4419.0),
    ]
    # avg entry 4427.5, risk $6 -> needs ask <= 4421.5
    fake = FakeMt5(positions=positions, bid=4421.3, ask=4421.5)
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="SELL", magic=990000, sl_pips=60)

    applied = executor.check_average_breakeven(campaign, risk_reward_trigger=1.0)

    assert applied is True
    assert all(req["sl"] == 4427.5 for req in fake.sent_requests)


def test_campaign_has_open_trades_true_with_pending_orders():
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, orders=[FakeOrder(ticket=1, magic=990000)])
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is True


def test_campaign_has_open_trades_true_with_open_positions():
    positions = [FakePosition(ticket=1, magic=990000, price_open=4420.0, volume=0.01, tp=4426.0)]
    fake = FakeMt5(positions=positions, bid=4420.0, ask=4420.2, orders=[])
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is True


def test_campaign_has_open_trades_false_once_everything_closed():
    fake = FakeMt5(positions=[], bid=4420.0, ask=4420.2, orders=[])
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is False


def test_campaign_has_open_trades_ignores_other_campaigns_magic():
    fake = FakeMt5(
        positions=[FakePosition(ticket=1, magic=111111, price_open=4420.0, volume=0.01, tp=4426.0)],
        bid=4420.0, ask=4420.2,
        orders=[FakeOrder(ticket=2, magic=222222)],
    )
    executor = _executor_with(fake)
    campaign = Campaign(id="c1", symbol="XAUUSD", direction="BUY", magic=990000, sl_pips=60)

    assert executor.campaign_has_open_trades(campaign) is False
