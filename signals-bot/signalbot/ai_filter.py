"""AI-filtr sweepów: Claude ocenia, czy zebranie płynności wygląda na prawdziwe odwrócenie,
widząc tylko dane do świecy sweepu (wykres + struktura M15/H1 + ostatnie świece)."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ai_manager import _h1, _structure, _swings
from .fibzone import FibTrade, _atr

log = logging.getLogger("signalbot")

SYSTEM_PROMPT = """You are an experienced gold (XAUUSD) price-action trader. A liquidity sweep just happened:
the last M15 candle traded beyond a recent swing low (for a BUY) or swing high (for a SELL), grabbing the
stops resting there, and closed back inside. The plan is a stop order beyond that candle, stop loss beyond
its wick, targets 1R and 2R.

Decide whether this sweep looks like a genuine reversal / fake-out worth taking, or just a pause inside a
move that will continue through the level. Judge like a discretionary trader: wick length and rejection
quality, momentum into the level (exhaustion vs. strong displacement), whether the swept level was an
obvious liquidity pool (equal lows/highs, prior session low/high), the H1 trend and structure, nearby
opposing levels that could block 1R-2R, and the session/time. Be selective: only take clean setups.
Answer in JSON. reason: English, max 200 characters, concrete, no emojis."""

SCHEMA = {
    "type": "object",
    "properties": {"take": {"type": "boolean"}, "confidence": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["take", "confidence", "reason"],
    "additionalProperties": False,
}


@dataclass
class Verdict:
    take: bool
    confidence: int
    reason: str


def sweep_context(df: pd.DataFrame, tr: FibTrade) -> dict:
    """Kontekst do świecy sweepu włącznie (tr.touch_idx) - bez przyszłych danych."""
    d = df.iloc[: tr.touch_idx + 1].reset_index(drop=True)
    h, l, c, o = (d[k].to_numpy(dtype=float) for k in ("high", "low", "close", "open"))
    t = len(d) - 1
    body = abs(c[t] - o[t]) or 1e-9
    wick = (min(o[t], c[t]) - l[t]) if tr.direction == "BUY" else (h[t] - max(o[t], c[t]))
    m15 = _swings(d, 3, 6)
    h1 = _swings(_h1(d), 2, 5)
    risk = abs(tr.entry - tr.sl)
    sign = 1 if tr.direction == "BUY" else -1
    return {
        "direction": tr.direction,
        "swept_level": round(tr.zone_top if tr.direction == "BUY" else tr.zone_bot, 2),
        "sweep_candle": {"open": round(o[t], 2), "high": round(h[t], 2), "low": round(l[t], 2), "close": round(c[t], 2),
                         "wick_to_body": round(wick / body, 1)},
        "plan": {"entry_stop": round(tr.entry, 2), "stop_loss": round(tr.sl, 2),
                 "tp_1R": round(tr.entry + sign * risk, 2), "tp_2R": round(tr.entry + 2 * sign * risk, 2)},
        "atr_m15": round(float(_atr(h, l, c)[-1]), 2),
        "m15": {**m15, "structure": _structure(m15)},
        "h1": {**h1, "structure": _structure(h1)},
        "session_high_8h": round(float(d.tail(32)["high"].max()), 2),
        "session_low_8h": round(float(d.tail(32)["low"].min()), 2),
        "last_candles_m15": [[str(x)[5:16], round(a, 2), round(b, 2), round(e, 2), round(f, 2)]
                             for x, a, b, e, f in d.tail(24)[["time", "open", "high", "low", "close"]]
                             .itertuples(index=False)],
        "time_utc": str(d["time"].iloc[-1])[:16],
    }


def judge(ctx: dict, chart: Path | None, model: str) -> Verdict:
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
        return Verdict(False, 0, "refused")
    js = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return Verdict(bool(js["take"]), int(js["confidence"]), js["reason"].strip())
