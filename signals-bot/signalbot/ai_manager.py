"""AI-menedżer otwartej pozycji: patrzy na całą strukturę rynku (M15 + H1, swingi, BOS/CHoCH,
strefy, Volume Profile, ostatnie świece, wykres) i decyduje jak doświadczony trader:
trzymać, przesunąć SL na istotny poziom, zrealizować część zysku albo zamknąć całość.

Wejście i początkowe poziomy daje strategia. AI tylko zarządza pozycją, która już jest na zysku.
Bezpieczniki w kodzie: SL wolno tylko zacieśniać (nigdy nie oddalać), musi być po właściwej stronie
ceny z buforem, partial w granicach 10–90%. Błąd lub brak klucza API = "hold".
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .fibzone import FibTrade, _atr
from .structure import find_swings, volume_profile

log = logging.getLogger("signalbot")

SYSTEM_PROMPT = """You are a senior discretionary trader on a Wall Street macro desk, managing an OPEN
gold (XAUUSD) position that a systematic strategy entered. The entry was good; your job is to manage the
trade like a professional: let winners run while the structure supports the trade, and protect or bank
profit when the market tells you the move is ending.

Read the WHOLE picture, not only the strategy levels: higher-timeframe (H1) trend and swing sequence,
M15 market structure (higher highs/lows, BOS, CHoCH against the trade), liquidity resting above swing
highs / below swing lows, supply/demand zones, Volume Profile (POC, value area edges) as magnets or walls,
momentum and candle behaviour (rejection wicks, engulfing, displacement), and how far price already
travelled versus its ATR.

Actions:
- hold: structure still supports the trade, nothing to do.
- move_sl: trail the stop to a MEANINGFUL level - just beyond a confirmed swing that protects the trend,
  beyond a zone, or beyond POC/VA edge - never into the middle of noise. Typical buffer 0.2-0.5 ATR.
- partial: bank part of the position into a strong opposing level (HTF swing, zone, VA edge, liquidity
  pool) or after a strong rejection, while the bigger picture still allows more.
- close: exit everything - clear reversal (CHoCH against the trade with displacement, HTF level rejection,
  structure broken).
Do not micro-manage: if in doubt, hold. Do not move the stop every candle. Never widen the stop.
Answer in JSON. reason: English, one or two short sentences, max 220 characters, concrete (name the level
or structure), no emojis, no hype - it is published to the channel."""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["hold", "move_sl", "partial", "close"]},
        "new_sl": {"type": ["number", "null"]},
        "close_pct": {"type": ["integer", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "new_sl", "close_pct", "reason"],
    "additionalProperties": False,
}


@dataclass
class Decision:
    action: str
    new_sl: float | None = None
    close_pct: int | None = None
    reason: str = ""


def _swings(df: pd.DataFrame, n: int, k: int) -> dict:
    highs, lows = find_swings(df, n)
    end = len(df) - 1
    fmt = lambda s: {"price": round(s.price, 2), "time": str(df["time"].iloc[s.idx])[:16]}  # noqa: E731
    return {"swing_highs": [fmt(s) for s in highs if s.confirmed_at <= end][-k:],
            "swing_lows": [fmt(s) for s in lows if s.confirmed_at <= end][-k:]}


def _structure(sw: dict) -> str:
    hs = [s["price"] for s in sw["swing_highs"][-3:]]
    ls = [s["price"] for s in sw["swing_lows"][-3:]]
    if len(hs) < 2 or len(ls) < 2:
        return "unclear"
    up, down = hs[-1] > hs[-2] and ls[-1] > ls[-2], hs[-1] < hs[-2] and ls[-1] < ls[-2]
    return "bullish (HH/HL)" if up else "bearish (LH/LL)" if down else "ranging / mixed"


def _h1(df: pd.DataFrame) -> pd.DataFrame:
    d = df.set_index("time").resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d.reset_index()


def build_context(df: pd.DataFrame, tr: FibTrade, rec: dict, cur_sl: float, left: float, entry: float,
                  pip: float) -> dict:
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    atr = float(_atr(h, l, c)[-1])
    price = float(c[-1])
    buy = tr.direction == "BUY"
    risk = abs(entry - tr.sl)
    m15 = _swings(df, 3, 6)
    h1df = _h1(df)
    h1 = _swings(h1df, 2, 5)
    prof = volume_profile(df, len(df) - 1, 200)
    since = df.iloc[tr.entry_idx :]
    best = float(since["high"].max() if buy else since["low"].min())
    last = df.tail(16)
    return {
        "position": {
            "direction": tr.direction, "entry": round(entry, 2), "current_stop": round(cur_sl, 2),
            "initial_stop": round(tr.sl, 2), "remaining_position_pct": round(left * 100),
            "targets_left": [round(x, 2) for x in rec.get("tps_left", [])],
            "targets_hit": rec.get("tp_hit", 0), "price_now": round(price, 2),
            "open_profit_pips": round(((price - entry) if buy else (entry - price)) / pip),
            "open_profit_R": round(((price - entry) if buy else (entry - price)) / risk, 2),
            "best_price_since_entry": round(best, 2), "candles_in_trade": len(since) - 1,
        },
        "atr_m15": round(atr, 2),
        "m15": {**m15, "structure": _structure(m15)},
        "h1": {**h1, "structure": _structure(h1),
               "last_close": round(float(h1df["close"].iloc[-1]), 2) if len(h1df) else None},
        "entry_zone": [round(tr.zone_bot, 2), round(tr.zone_top, 2)],
        "volume_profile": None if prof is None else {"poc": round(prof.poc, 2), "val": round(prof.val, 2),
                                                     "vah": round(prof.vah, 2)},
        "session_high": round(float(df.tail(32)["high"].max()), 2),
        "session_low": round(float(df.tail(32)["low"].min()), 2),
        "last_candles_m15": [[str(t)[11:16], round(o, 2), round(hh, 2), round(ll, 2), round(cc, 2)]
                             for t, o, hh, ll, cc in last[["time", "open", "high", "low", "close"]].itertuples(index=False)],
        "time_utc": str(df["time"].iloc[-1])[:16],
    }


def ask_ai(ctx: dict, chart: Path | None, model: str) -> Decision:
    import anthropic

    content = []
    if chart is not None and Path(chart).exists():
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.standard_b64encode(Path(chart).read_bytes()).decode()}})
    content.append({"type": "text", "text": json.dumps(ctx)})
    resp = anthropic.Anthropic().beta.messages.create(
        model=model, max_tokens=8000, system=SYSTEM_PROMPT,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        return Decision("hold")
    js = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return Decision(js["action"], js.get("new_sl"), js.get("close_pct"), js.get("reason", "").strip())


def validate(d: Decision, direction: str, cur_sl: float, price: float, atr: float, left: float) -> Decision:
    """Bezpieczniki: SL tylko bliżej ceny niż obecny i z buforem, partial 10–90%, ostatnia część = close."""
    buy = direction == "BUY"
    if d.action == "move_sl":
        sl = d.new_sl
        ok = sl is not None and np.isfinite(sl) and (
            (buy and cur_sl < sl < price - 0.15 * atr) or (not buy and price + 0.15 * atr < sl < cur_sl))
        if not ok:
            log.info("AI: odrzucony SL %s (obecny %.2f, cena %.2f)", sl, cur_sl, price)
            return Decision("hold", reason=d.reason)
    if d.action == "partial":
        pct = int(d.close_pct or 0)
        if pct >= 90 or left <= 0.25:
            return replace(d, action="close")
        if pct < 10:
            return Decision("hold", reason=d.reason)
        d = replace(d, close_pct=pct)
    return d


def decide(cfg, df: pd.DataFrame, tr: FibTrade, rec: dict, cur_sl: float, left: float, entry: float) -> Decision:
    ctx = build_context(df, tr, rec, cur_sl, left, entry, cfg.pip_size)
    chart = None
    try:
        from .chart_tv import render_post_chart

        chart = render_post_chart(df, replace(tr, entry_idx=len(df) - 1),
                                  cfg.data_dir / "charts" / "ai_manage.png", cfg.display_symbol, cfg.timeframe,
                                  handle=cfg.handle, source=cfg.chart_source)
    except Exception as e:  # wykres pomocniczy - bez niego AI i tak ma pełne dane
        log.warning("AI: wykres niedostępny: %s", e)
    try:
        d = ask_ai(ctx, chart, cfg.anthropic_model)
    except Exception as e:
        log.warning("AI-menedżer niedostępny (%s) - trzymam pozycję", e)
        return Decision("hold")
    log.info("AI decyzja %s: %s sl=%s pct=%s | %s", tr.id, d.action, d.new_sl, d.close_pct, d.reason)
    return validate(d, tr.direction, cur_sl, ctx["position"]["price_now"], ctx["atr_m15"], left)
