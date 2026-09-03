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

    symbol: str
    lot_size: float
    zone_step: float
    pip_size: float
    start_tp_pips: float
    tp_increment_pips: float
    deviation_points: int
    magic_base: int

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
        symbol=os.getenv("SYMBOL", "XAUUSD"),
        lot_size=_float("LOT_SIZE", 0.01),
        zone_step=_float("ZONE_STEP", 0.5),
        pip_size=_float("PIP_SIZE", 0.1),
        start_tp_pips=_float("START_TP_PIPS", 60),
        tp_increment_pips=_float("TP_INCREMENT_PIPS", 10),
        deviation_points=_int("DEVIATION_POINTS", 20),
        magic_base=_int("MAGIC_BASE", 990000),
        dry_run=_bool("DRY_RUN", True),
    )
