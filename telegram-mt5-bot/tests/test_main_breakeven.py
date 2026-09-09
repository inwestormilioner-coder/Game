"""Verifies the bot ignores the channel's "SL na BE" and "Zamykam calosc"
instructions - it only creates campaign state on ZONE messages and never
touches it from update messages. The average-entry breakeven logic and the
own-state campaign-finished detection live in mt5_executor and are covered
separately."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign_store import CampaignStore  # noqa: E402
from config import Config  # noqa: E402
from main import Bot  # noqa: E402


def _dry_run_config(**overrides) -> Config:
    base = dict(
        telegram_api_id=0, telegram_api_hash="", telegram_session_name="x", telegram_channel="",
        mt5_path="", mt5_login=0, mt5_password="", mt5_server="", bridge_subfolder="tg_bridge",
        symbol="XAUUSD", lot_size=0.01, lot_tier_orders=3, lot_scaling_mode="additive", lot_multiplier=1.2,
        zone_step=0.5, pip_size=0.1,
        start_tp_pips=60, tp_increment_pips=10, tp_mode="ladder", tp_risk_reward_ratio=1.0,
        exit_mode="tp", trailing_stop_pips=36.0,
        deviation_points=20, magic_base=990000,
        max_zone_width=20.0, risk_reward_trigger=1.0, monitor_interval_seconds=5, dry_run=True,
    )
    base.update(overrides)
    return Config(**base)


def test_breakeven_message_leaves_campaign_untouched(tmp_path):
    store = CampaignStore(path=tmp_path / "campaigns.json")
    bot = Bot(_dry_run_config(), store=store)

    asyncio.run(bot.handle_text("Kierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips"))
    campaigns_before = store.most_recent_active("XAUUSD")
    assert len(campaigns_before) == 1
    assert campaigns_before[0].sl_pips == 60.0
    assert campaigns_before[0].breakeven_applied is False

    asyncio.run(bot.handle_text("TAKE PROFIT: +70 pips SL na BE juz mozliwy. Zbieram malutka czesc zyskow."))

    campaigns_after = store.most_recent_active("XAUUSD")
    assert len(campaigns_after) == 1
    assert campaigns_after[0].active is True
    assert campaigns_after[0].breakeven_applied is False  # channel message did NOT touch this
    assert campaigns_after[0].tickets == campaigns_before[0].tickets


def test_close_all_message_leaves_campaign_untouched(tmp_path):
    store = CampaignStore(path=tmp_path / "campaigns.json")
    bot = Bot(_dry_run_config(), store=store)

    asyncio.run(bot.handle_text("Kierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips"))
    asyncio.run(bot.handle_text("TAKE PROFIT: +140 pips Zamykam calosc. Podsylajcie wyniki!"))

    # the campaign is only ever deactivated by monitor_campaigns() noticing
    # MT5 has no open trades left for it - never by the channel's message
    campaigns = store.most_recent_active("XAUUSD")
    assert len(campaigns) == 1
    assert campaigns[0].active is True


def test_refuses_a_zone_wider_than_max_zone_width(tmp_path):
    # Regression-style guard for a live incident: a parser bug once misread
    # "Strefa: 4397-02" as a $100-wide zone (4302-4402) instead of $5
    # (4397-4402), which would have fired ~200 orders instead of ~11. This
    # test exercises the width guard directly with a full 4-digit second
    # number (so it's a $150 zone regardless of the tail-matching math).
    store = CampaignStore(path=tmp_path / "campaigns.json")
    bot = Bot(_dry_run_config(max_zone_width=20.0), store=store)

    asyncio.run(bot.handle_text("Kierunek: Sell Gold\nStrefa: 4450-4300\nSL: 60 pips"))

    assert store.most_recent_active("XAUUSD") == []


def test_accepts_a_normal_width_zone_at_the_limit(tmp_path):
    store = CampaignStore(path=tmp_path / "campaigns.json")
    bot = Bot(_dry_run_config(max_zone_width=20.0), store=store)

    asyncio.run(bot.handle_text("Kierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips"))

    assert len(store.most_recent_active("XAUUSD")) == 1
