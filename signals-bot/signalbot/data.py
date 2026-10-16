"""Źródła danych OHLC. Każde zwraca DataFrame: time (UTC), open, high, low, close
— tylko zamknięte świece, od najstarszej."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}


def _only_closed(df: pd.DataFrame, timeframe: str, now: datetime | None = None) -> pd.DataFrame:
    now = now or datetime.now(timezone.utc)
    close_time = df["time"] + pd.Timedelta(minutes=TF_MINUTES[timeframe])
    return df[close_time <= pd.Timestamp(now)].reset_index(drop=True)


class MT5Provider:
    """MetaTrader 5 (np. konto Exness). Pakiet `MetaTrader5` działa tylko na Windows
    z zainstalowanym terminalem MT5. Symbol jak w terminalu, np. `XAUUSDm` na Exness."""

    def __init__(self, login: int | None = None, password: str | None = None,
                 server: str | None = None, path: str | None = None):
        import MetaTrader5 as mt5  # noqa: import tylko gdy używany

        self.mt5 = mt5
        kwargs = {k: v for k, v in dict(login=login, password=password, server=server).items() if v}
        ok = mt5.initialize(path, **kwargs) if path else mt5.initialize(**kwargs)
        if not ok:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    def get_bars(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}")
        self.mt5.symbol_select(symbol, True)
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 0, count + 1)
        if rates is None:
            raise RuntimeError(f"MT5 copy_rates failed: {self.mt5.last_error()}")
        df = pd.DataFrame(rates)
        # Czas świec w MT5 to czas serwera brokera (Exness = UTC).
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df[["time", "open", "high", "low", "close"]].iloc[:-1]  # ostatnia świeca jeszcze się tworzy
        return df.reset_index(drop=True)


class TwelveDataProvider:
    """https://twelvedata.com — działa na dowolnym serwerze (Linux). Symbol `XAU/USD`.
    1 zapytanie co 30 min = 48/dzień, mieści się w darmowym limicie."""

    URL = "https://api.twelvedata.com/time_series"
    INTERVALS = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h"}

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_bars(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        r = requests.get(
            self.URL,
            params=dict(symbol=symbol, interval=self.INTERVALS[timeframe], outputsize=count + 1,
                        timezone="UTC", order="ASC", apikey=self.api_key),
            timeout=30,
        )
        r.raise_for_status()
        js = r.json()
        if js.get("status") != "ok":
            raise RuntimeError(f"Twelve Data: {js.get('message', js)}")
        df = pd.DataFrame(js["values"])
        df["time"] = pd.to_datetime(df["datetime"], utc=True)
        for k in ("open", "high", "low", "close"):
            df[k] = df[k].astype(float)
        return _only_closed(df[["time", "open", "high", "low", "close"]], timeframe)


class CSVProvider:
    """Plik CSV z kolumnami time,open,high,low,close (np. eksport z MT5) — do backtestu."""

    def __init__(self, path: str):
        self.path = path

    def get_bars(self, symbol: str, timeframe: str, count: int | None = None) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        df.columns = [c.strip().lower().strip("<>") for c in df.columns]
        for alt in ("datetime", "date"):
            if "time" not in df.columns and alt in df.columns:
                df["time"] = df[alt]
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)
        return df.tail(count).reset_index(drop=True) if count else df


class SyntheticProvider:
    """Losowe dane przypominające złoto — tylko do testów bez dostępu do rynku."""

    def __init__(self, seed: int = 7, start_price: float = 4150.0):
        self.seed, self.start_price = seed, start_price

    def get_bars(self, symbol: str, timeframe: str, count: int = 2000) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed)
        # zmienny dryf, żeby powstawały trendy i korekty
        drift = np.repeat(rng.normal(0, 0.8, count // 40 + 1), 40)[:count]
        steps = drift + rng.normal(0, 3.0, count)
        close = self.start_price + np.cumsum(steps)
        open_ = np.r_[self.start_price, close[:-1]]
        wick = np.abs(rng.normal(0, 2.0, (2, count)))
        high = np.maximum(open_, close) + wick[0]
        low = np.minimum(open_, close) - wick[1]
        end = pd.Timestamp(datetime.now(timezone.utc)).floor(f"{TF_MINUTES[timeframe]}min")
        times = pd.date_range(end=end - timedelta(minutes=TF_MINUTES[timeframe]),
                              periods=count, freq=f"{TF_MINUTES[timeframe]}min")
        return pd.DataFrame(dict(time=times, open=open_, high=high, low=low, close=close))


def make_provider(cfg) -> object:
    if cfg.data_source == "mt5":
        return MT5Provider(cfg.mt5_login, cfg.mt5_password, cfg.mt5_server, cfg.mt5_path)
    if cfg.data_source == "twelvedata":
        return TwelveDataProvider(cfg.twelvedata_api_key)
    if cfg.data_source == "csv":
        return CSVProvider(cfg.csv_path)
    if cfg.data_source == "synthetic":
        return SyntheticProvider()
    raise ValueError(f"Nieznane DATA_SOURCE: {cfg.data_source}")
