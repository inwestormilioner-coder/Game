"""Verifies the bot ignores the channel's "SL na BE" instruction and only
touches campaign state on ZONE / CLOSE_ALL messages - the average-entry
breakeven logic itself lives in mt5_executor and is covered separately."""
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
        mt5_path="", mt5_login=0, mt5_password="", mt5_server="",
        symbol="XAUUSD", lot_size=0.01, zone_step=0.5, pip_size=0.1,
        start_tp_pips=60, tp_increment_pips=10, deviation_points=20, magic_base=990000,
        risk_reward_trigger=1.0, monitor_interval_seconds=5, dry_run=True,
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


def test_close_all_still_deactivates_campaign(tmp_path):
    store = CampaignStore(path=tmp_path / "campaigns.json")
    bot = Bot(_dry_run_config(), store=store)

    asyncio.run(bot.handle_text("Kierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips"))
    asyncio.run(bot.handle_text("TAKE PROFIT: +140 pips Zamykam calosc. Podsylajcie wyniki!"))

    assert store.most_recent_active("XAUUSD") == []
