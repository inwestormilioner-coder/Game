"""Konfiguracja z pliku .env / zmiennych środowiskowych."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in ("1", "true", "yes", "tak")


@dataclass
class Config:
    symbol: str = "XAU/USD"
    display_symbol: str = "XAUUSD"
    timeframe: str = "M30"
    bars: int = 500
    data_source: str = "twelvedata"

    mt5_login: int | None = None
    mt5_password: str = ""
    mt5_server: str = ""
    mt5_path: str = ""
    mt5_utc_offset: float | None = None  # None = wykryj automatycznie
    min_sl: float = 3.0                  # min. odległość SL od wejścia (w cenie, np. 3.0 = 3$ na złocie)
    twelvedata_api_key: str = ""
    csv_path: str = ""

    min_rr: float = 1.5
    min_score: int = 0          # minimalna liczba konfluencji (Fibo / FVG / sweep)
    tp_mode: str = "impulse"    # impulse | liquidity
    strategy: str = "fibzone"   # fibzone (strefa + Fibo) | smc (BOS/CHOCH + retest)
    invite_url: str = ""        # link do grupy Telegram w postach na X / Threads
    handle: str = ""            # znak wodny na wykresie, np. @TwojNick
    chart_source: str = ""      # podpis źródła na wykresie, np. RoboForex
    chart_mode: str = "render"  # render = własny wykres | tradingview = zrzut Twojego layoutu TV
    tv_chart_url: str = ""      # adres Twojego layoutu, np. https://www.tradingview.com/chart/AbCdEfGh/
    tv_symbol: str = "OANDA:XAUUSD"
    tv_profile_dir: str = "tv_profile"
    ai_exit: bool = True        # zamknij na zysku przy odwróceniu struktury (z info pod sygnałem)
    ai_exit_min_r: float = 0.5  # minimalny zysk w R, żeby wyjść
    ai_manager: bool = True     # AI-trader zarządza pozycją na zysku (SL na poziomy, partiale, wyjście)
    ai_manager_min_r: float = 0.5
    summary_hour_utc: int = 21  # godzina (UTC) podsumowania dnia; w piątek także tygodnia
    reply_losses: bool = False  # odpowiadać pod postem także przy stracie
    pip_size: float = 0.1       # wielkość pipsa (złoto: 0.10$)
    tp_levels: tuple = (0.382, 0.618, 1.0, 1.272, 1.618)  # cele Fibo (strategia fibzone)
    language: str = "pl"
    use_ai: bool = True
    anthropic_model: str = "claude-opus-5-5"

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    threads_enabled: bool = False
    threads_user_id: str = ""
    threads_access_token: str = ""
    public_image_base_url: str = ""   # Threads wymaga obrazka pod publicznym URL
    imgbb_api_key: str = ""           # bez publicznego URL: upload na imgbb (z kluczem) albo catbox

    x_enabled: bool = False
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_secret: str = ""

    trade_enabled: bool = False       # auto-trading sygnałów na koncie MT5
    trade_symbol: str = ""            # symbol u brokera do handlu (puste = SYMBOL)
    trade_risk_pct: float = 1.0       # ryzyko na sygnał w % salda (dzielone na wszystkie TP)
    trade_lot: float = 0.0            # >0 = stały lot na każde zlecenie zamiast % ryzyka
    trade_magic: int = 770077
    trade_allow_real: bool = False    # bez tego bot gra wyłącznie na koncie demo
    trade_mt5_path: str = ""          # osobny terminal do handlu (np. Vantage), puste = ten sam co dane
    trade_mt5_login: int | None = None
    trade_mt5_password: str = ""
    trade_mt5_server: str = ""

    dry_run: bool = True
    data_dir: Path = field(default_factory=lambda: Path("data"))


def strategy_params(cfg: Config):
    from .strategy import Params

    return Params(min_rr=cfg.min_rr, min_score=cfg.min_score, tp_mode=cfg.tp_mode)


def load_config(env_file: str | None = ".env") -> Config:
    if env_file:
        _load_dotenv(Path(env_file))
    login = _env("MT5_LOGIN")
    return Config(
        symbol=_env("SYMBOL", "XAU/USD"),
        display_symbol=_env("DISPLAY_SYMBOL", "XAUUSD"),
        timeframe=_env("TIMEFRAME", "M30"),
        bars=int(_env("BARS", "500")),
        data_source=_env("DATA_SOURCE", "twelvedata"),
        mt5_login=int(login) if login else None,
        mt5_password=_env("MT5_PASSWORD"),
        mt5_server=_env("MT5_SERVER"),
        mt5_path=_env("MT5_PATH"),
        mt5_utc_offset=float(_env("MT5_UTC_OFFSET")) if _env("MT5_UTC_OFFSET") else None,
        min_sl=float(_env("MIN_SL", "3.0")),
        twelvedata_api_key=_env("TWELVEDATA_API_KEY"),
        csv_path=_env("CSV_PATH"),
        min_rr=float(_env("MIN_RR", "1.5")),
        min_score=int(_env("MIN_SCORE", "0")),
        tp_mode=_env("TP_MODE", "impulse"),
        strategy=_env("STRATEGY", "fibzone"),
        invite_url=_env("TELEGRAM_INVITE_URL"),
        handle=_env("CHART_HANDLE"),
        chart_source=_env("CHART_SOURCE"),
        chart_mode=_env("CHART_MODE", "render"),
        tv_chart_url=_env("TV_CHART_URL"),
        tv_symbol=_env("TV_SYMBOL", "OANDA:XAUUSD"),
        tv_profile_dir=_env("TV_PROFILE_DIR", "tv_profile"),
        ai_exit=_bool("AI_EXIT", True),
        ai_exit_min_r=float(_env("AI_EXIT_MIN_R", "0.5")),
        ai_manager=_bool("AI_MANAGER", True),
        ai_manager_min_r=float(_env("AI_MANAGER_MIN_R", "0.5")),
        summary_hour_utc=int(_env("SUMMARY_HOUR_UTC", "21")),
        reply_losses=_bool("REPLY_LOSSES", False),
        pip_size=float(_env("PIP_SIZE", "0.1")),
        tp_levels=tuple(float(x) for x in _env("TP_LEVELS", "0.382,0.618,1.0,1.272,1.618").split(",")),
        language=_env("POST_LANGUAGE", "pl"),
        use_ai=_bool("USE_AI", True),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-opus-5-5"),
        telegram_enabled=_bool("TELEGRAM_ENABLED"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        threads_enabled=_bool("THREADS_ENABLED"),
        threads_user_id=_env("THREADS_USER_ID"),
        threads_access_token=_env("THREADS_ACCESS_TOKEN"),
        public_image_base_url=_env("PUBLIC_IMAGE_BASE_URL").rstrip("/"),
        imgbb_api_key=_env("IMGBB_API_KEY"),
        x_enabled=_bool("X_ENABLED"),
        x_api_key=_env("X_API_KEY"),
        x_api_secret=_env("X_API_SECRET"),
        x_access_token=_env("X_ACCESS_TOKEN"),
        x_access_secret=_env("X_ACCESS_SECRET"),
        trade_enabled=_bool("TRADE_ENABLED"),
        trade_symbol=_env("TRADE_SYMBOL"),
        trade_risk_pct=float(_env("TRADE_RISK_PCT", "1.0")),
        trade_lot=float(_env("TRADE_LOT", "0") or 0),
        trade_magic=int(_env("TRADE_MAGIC", "770077")),
        trade_allow_real=_bool("TRADE_ALLOW_REAL"),
        trade_mt5_path=_env("TRADE_MT5_PATH"),
        trade_mt5_login=int(_env("TRADE_MT5_LOGIN")) if _env("TRADE_MT5_LOGIN") else None,
        trade_mt5_password=_env("TRADE_MT5_PASSWORD"),
        trade_mt5_server=_env("TRADE_MT5_SERVER"),
        dry_run=_bool("DRY_RUN", True),
        data_dir=Path(_env("DATA_DIR", "data")),
    )
