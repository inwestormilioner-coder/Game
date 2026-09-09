"""Loads bot configuration from environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass(frozen=True)
class Config:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str
    telegram_channel: str

    mt5_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    # Subfolder under MT5's shared Common\Files where command files for the
    # EA are dropped. MT5's Common folder is shared by EVERY terminal
    # install on the machine, so running a second bot instance against a
    # second MT5 account needs a different value here (and a matching
    # TelegramBridgeEA BridgeSubfolder input on that account's chart) - two
    # instances sharing the default would cross-talk.
    bridge_subfolder: str

    symbol: str
    lot_size: float
    lot_tier_orders: int
    # "additive" (default) - each tier adds +1 more lot_size step.
    # "multiplier" - each tier is lot_multiplier times the previous one
    # (compounding), e.g. 0.1 -> 0.12 -> 0.144 -> ... for lot_multiplier=1.2.
    lot_scaling_mode: str
    lot_multiplier: float
    zone_step: float
    # Extra orders beyond the signal's own zone, SL unaffected (still
    # anchored to the signal's zone_low/zone_high): zone_extend_front adds
    # orders past the edge closest to current price (catches a fill missed
    # by spread), zone_extend_back adds orders past the edge closest to SL.
    # Both in dollars, 0 = no extension (exactly the signal's zone).
    zone_extend_front: float
    zone_extend_back: float
    pip_size: float
    start_tp_pips: float
    tp_increment_pips: float
    # "ladder" (start_tp_pips/tp_increment_pips above) or "risk_reward" -
    # each order's TP set to tp_risk_reward_ratio times ITS OWN distance to
    # the shared SL (1.0 = 1:1), which varies per order since SL is one
    # fixed price but entries sit at different distances from it.
    tp_mode: str
    tp_risk_reward_ratio: float
    # "tp" (default) - each order gets a TP as above, no continuous SL
    # trailing beyond the one-time basket-average move at risk_reward_trigger.
    # "trailing_stop" - orders get NO fixed TP at all; instead every open
    # position's own SL continuously trails trailing_stop_pips behind
    # price (tightening only, never loosening), independent of every other
    # position and NOT combined with the basket-average-at-1:1 move.
    exit_mode: str
    trailing_stop_pips: float
    deviation_points: int
    magic_base: int
    # Safety net against a misparsed/malformed zone turning into a huge
    # order count (e.g. a parser bug once misread "4397-02" as a $100-wide
    # zone instead of $5, firing ~200 orders instead of ~11) - a zone wider
    # than this is refused rather than acted on.
    max_zone_width: float

    # Own SL management: the bot ignores the channel's "SL na BE" messages
    # and instead moves SL to the basket's average entry price once floating
    # profit reaches risk_reward_trigger * initial risk (1.0 = 1:1).
    risk_reward_trigger: float
    monitor_interval_seconds: float

    # Telegram notifications (fills + daily summary) - uses the SAME
    # logged-in Telethon session that reads the signal channel, no separate
    # bot needed. Only active when dry_run is False (needs a live MT5
    # connection to read fills/deal history) - see notifier.py, main.py's
    # Bot.watch_fills/daily_summary_loop, and mt5_executor's
    # take_pending_fill_notifications/position_details/daily_stats.
    notify_enabled: bool
    telegram_notify_chat: str
    # Local time (24h "HH:MM") the daily pips/profit summary is sent.
    daily_summary_time: str

    dry_run: bool


def load_config() -> Config:
    return Config(
        telegram_api_id=_int("TELEGRAM_API_ID", 0),
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", ""),
        telegram_session_name=os.getenv("TELEGRAM_SESSION_NAME", "signal_bot"),
        telegram_channel=os.getenv("TELEGRAM_CHANNEL", ""),
        mt5_path=os.getenv("MT5_PATH", ""),
        mt5_login=_int("MT5_LOGIN", 0),
        mt5_password=os.getenv("MT5_PASSWORD", ""),
        mt5_server=os.getenv("MT5_SERVER", ""),
        bridge_subfolder=os.getenv("MT5_BRIDGE_SUBFOLDER", "tg_bridge"),
        symbol=os.getenv("SYMBOL", "XAUUSD"),
        lot_size=_float("LOT_SIZE", 0.01),
        lot_tier_orders=_int("LOT_TIER_ORDERS", 3),
        lot_scaling_mode=os.getenv("LOT_SCALING_MODE", "additive"),
        lot_multiplier=_float("LOT_MULTIPLIER", 1.2),
        zone_step=_float("ZONE_STEP", 0.5),
        zone_extend_front=_float("ZONE_EXTEND_FRONT", 0.0),
        zone_extend_back=_float("ZONE_EXTEND_BACK", 0.0),
        pip_size=_float("PIP_SIZE", 0.1),
        start_tp_pips=_float("START_TP_PIPS", 60),
        tp_increment_pips=_float("TP_INCREMENT_PIPS", 10),
        tp_mode=os.getenv("TP_MODE", "risk_reward"),
        tp_risk_reward_ratio=_float("TP_RISK_REWARD_RATIO", 1.0),
        exit_mode=os.getenv("EXIT_MODE", "tp"),
        trailing_stop_pips=_float("TRAILING_STOP_PIPS", 36.0),
        deviation_points=_int("DEVIATION_POINTS", 20),
        magic_base=_int("MAGIC_BASE", 990000),
        max_zone_width=_float("MAX_ZONE_WIDTH", 20.0),
        risk_reward_trigger=_float("RISK_REWARD_TRIGGER", 1.0),
        monitor_interval_seconds=_float("MONITOR_INTERVAL_SECONDS", 5),
        notify_enabled=_bool("NOTIFY_ENABLED", True),
        telegram_notify_chat=os.getenv("TELEGRAM_NOTIFY_CHAT", "me"),
        daily_summary_time=os.getenv("DAILY_SUMMARY_TIME", "23:55"),
        dry_run=_bool("DRY_RUN", True),
    )
