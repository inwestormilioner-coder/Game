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
    zone_step: float
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
        zone_step=_float("ZONE_STEP", 0.5),
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
        dry_run=_bool("DRY_RUN", True),
    )
