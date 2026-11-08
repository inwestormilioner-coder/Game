"""Agenci AI dla formacji (Claude, z wykresem i danymi formacji):

1. Analityk (`analyst_verdict`) - jak AI-filtr sweepów: ocenia, czy formacja wykryta przez kod jest
   czytelna na wykresie i warta publikacji. Widzi tylko dane do świecy potwierdzenia.
2. Autor (`writer_why`) - jak w writer_fib: liczby wstawia kod, AI pisze tylko akapit "Why".

Bez klucza API / przy błędzie: analityk przepuszcza (None), autor używa szablonu.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ai_manager import _h1, _structure, _swings
from .patterns import HARMONICS, Pattern

log = logging.getLogger("signalbot")

ANALYST_PROMPT = """You are a senior technical analyst reviewing chart patterns that an algorithm detected on
gold (XAUUSD). You get the pattern as JSON (points, ratios, neckline or PRZ, the planned entry, stop and
targets, confluences with the trader's supply/demand zones, Fibonacci levels, Volume Profile and H1
structure) plus the chart. Pattern families:
- Double / triple top & bottom, head & shoulders (and inverse): confirmed by a candle close through the
  neckline; targets are the pattern height projected from the neckline (x1.0 and x1.618).
- Harmonic XABCD (Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark): D completed
  inside the Potential Reversal Zone and the candle rejected it; targets 0.382 and 0.618 of AD.
Judge like a discretionary trader would before posting it to a public channel: is the pattern clean and
obvious on the chart (well-defined swings, symmetric, not buried in noise), was there a real trend into it
(a reversal pattern needs something to reverse), does it form at a meaningful level (zone, Fib, POC),
is the H1 structure supportive or is the trade fighting a strong trend, is there room to the targets
before an opposing zone. Be selective - only clean, textbook patterns should be published.
Answer in JSON. grade: A (textbook), B (good), C (weak). reason: English, max 200 characters, concrete,
no emojis."""

ANALYST_SCHEMA = {
    "type": "object",
    "properties": {"take": {"type": "boolean"}, "confidence": {"type": "integer"},
                   "grade": {"type": "string", "enum": ["A", "B", "C"]}, "reason": {"type": "string"}},
    "required": ["take", "confidence", "grade", "reason"],
    "additionalProperties": False,
}

WRITER_PROMPT = """You write short, factual commentary for a gold (XAUUSD) trading channel. You get a chart
pattern detected by code (JSON) and its chart. Explain WHY the pattern is on the chart: how it formed
(the swings, the neckline break or the completion of D in the PRZ with the Fibonacci ratios that define
it), and which confluences support it (supply/demand zones, Fibonacci levels, Volume Profile, H1
structure). If something weakens it, say it plainly.
Rules: English only. No hype, no promises, no emojis. Do not list entry/SL/TP numbers; they are printed
separately. why_long: max 3 sentences, max 380 characters. why_short: one sentence, max 110 characters."""

WRITER_SCHEMA = {
    "type": "object",
    "properties": {"why_long": {"type": "string"}, "why_short": {"type": "string"}},
    "required": ["why_long", "why_short"],
    "additionalProperties": False,
}


@dataclass
class Verdict:
    take: bool
    confidence: int
    grade: str
    reason: str


def pattern_context(df: pd.DataFrame, pt: Pattern, symbol: str = "XAUUSD", timeframe: str = "M15") -> dict:
    """Dane dla agentów - tylko świece do potwierdzenia formacji włącznie."""
    d = df.iloc[: pt.confirm_idx + 1].reset_index(drop=True)
    t = lambda i: str(d["time"].iloc[i])[:16] if "time" in d.columns else str(i)  # noqa: E731
    m = _swings(d, 3, 6)
    ctx = {
        "symbol": symbol, "timeframe": timeframe,
        "pattern": pt.name, "family": pt.family, "direction": pt.direction,
        "points": [{"label": lab or "swing", "price": round(pr, 2), "time": t(i)} for i, pr, lab in pt.points],
        "plan": {"entry": round(pt.entry, 2), "stop_loss": round(pt.sl, 2),
                 "targets": [round(x, 2) for x in pt.tps], "rr_to_last_target": round(pt.rr, 2)},
        "confluences": pt.confluences,
        "confluence_score": pt.score,
        "details": pt.details,
        "time_utc": t(len(d) - 1),
    }
    if pt.family == "harmonic":
        g = HARMONICS[pt.kind]
        ctx["ratios"] = {"AB/XA": pt.ratios.get("b"), "BC/AB": pt.ratios.get("c"),
                         ("AD/XA" if g["d_of"] == "XA" else "CD/XC"): pt.ratios.get("d_xa" if g["d_of"] == "XA" else "d_xc"),
                         "CD/BC": pt.ratios.get("cd")}
        ctx["prz"] = [round(x, 2) for x in pt.prz]
        ctx["ideal_d_ratio"] = f"{g['d_ref']:g} {g['d_of']}"
    else:
        ctx["neckline"] = pt.details.get("neckline_break")
        ctx["pattern_height"] = pt.ratios.get("height")
    if "time" in d.columns and len(d) > 40:
        try:
            h1 = _swings(_h1(d), 2, 5)
            ctx["h1"] = {**h1, "structure": _structure(h1)}
        except Exception:  # noqa: BLE001 - brak wolumenu itp.
            pass
    ctx["m_tf"] = {**m, "structure": _structure(m)}
    ctx["last_candles"] = [[str(x)[5:16], round(a, 2), round(b, 2), round(e, 2), round(f, 2)]
                           for x, a, b, e, f in d.tail(20)[["time", "open", "high", "low", "close"]]
                           .itertuples(index=False)] if "time" in d.columns else []
    return ctx


def _ask(system: str, schema: dict, ctx: dict, chart: Path | None, model: str, effort: str, max_tokens: int):
    import anthropic

    content = []
    if chart is not None and Path(chart).exists():
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.standard_b64encode(Path(chart).read_bytes()).decode()}})
    content.append({"type": "text", "text": json.dumps(ctx, default=str)})
    resp = anthropic.Anthropic().beta.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def analyst_verdict(ctx: dict, chart: Path | None, model: str) -> Verdict | None:
    """Werdykt analityka albo None (brak klucza / błąd - wtedy formacja idzie bez filtra AI)."""
    try:
        js = _ask(ANALYST_PROMPT, ANALYST_SCHEMA, ctx, chart, model, "medium", 8000)
        return Verdict(bool(js["take"]), int(js["confidence"]), js["grade"], js["reason"].strip())
    except Exception as e:  # noqa: BLE001
        log.warning("AI-analityk formacji niedostępny: %s", e)
        return None


def template_why(pt: Pattern) -> tuple[str, str]:
    conf = "; ".join(pt.confluences) if pt.confluences else "no extra confluence"
    if pt.family == "harmonic":
        g = HARMONICS[pt.kind]
        lo, hi = pt.prz
        long = (f"A {pt.name} completed: point D reached the PRZ {lo:.2f}–{hi:.2f} defined by the "
                f"{g['d_ref']:g} {g['d_of']} ratio and the candle rejected it. Confluence: {conf}.")
        short = f"{pt.name} completed in the PRZ {lo:.2f}–{hi:.2f} and rejected it."
    else:
        neck = pt.details.get("neckline_break", 0.0)
        side = "below" if pt.direction == "SELL" else "above"
        long = (f"{pt.name}: price failed at the same level again and a candle closed {side} the neckline "
                f"{neck:.2f}. Targets are the pattern height projected from the neckline. Confluence: {conf}.")
        short = f"{pt.name} confirmed with a close {side} the neckline {neck:.2f}."
    return long[:380], short[:110]


def writer_why(ctx: dict, pt: Pattern, chart: Path | None, model: str, use_ai: bool) -> tuple[str, str]:
    if use_ai:
        try:
            js = _ask(WRITER_PROMPT, WRITER_SCHEMA, ctx, chart, model, "low", 4000)
            return js["why_long"].strip(), js["why_short"].strip()
        except Exception as e:  # noqa: BLE001
            log.warning("AI-autor niedostępny, szablon: %s", e)
    return template_why(pt)
