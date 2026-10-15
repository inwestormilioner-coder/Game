"""Treść posta. Liczby (wejście, SL, TP, RR) wstawia kod; AI pisze tylko uzasadnienie,
więc nie może pomylić poziomów."""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .strategy import Setup

log = logging.getLogger(__name__)

DISCLAIMER = {
    "pl": "⚠️ To nie jest porada inwestycyjna. Handel na dźwigni wiąże się z wysokim ryzykiem.",
    "en": "⚠️ Not financial advice. Leveraged trading carries a high level of risk.",
}


@dataclass
class Post:
    long: str     # Telegram (limit podpisu zdjęcia 1024 znaki)
    threads: str  # Threads (500)
    short: str    # X (280)


def _levels(s: Setup, symbol: str) -> str:
    arrow = "🔻" if s.direction == "SELL" else "🟢"
    zone = "Supply" if s.direction == "SELL" else "Demand"
    return (
        f"{symbol} {s.direction} SETUP {arrow}\n\n"
        f"Entry: {s.entry:.2f}\n"
        f"SL: {s.sl:.2f}\n"
        f"TP: {s.tp:.2f}\n"
        f"RR: 1:{s.rr:.1f}\n"
        f"{zone} zone: {s.zone_low:.2f}–{s.zone_high:.2f}\n"
        f"Structure: {s.break_type} @ {s.level:.2f}"
    )


def template_analysis(s: Setup, lang: str) -> tuple[str, str]:
    side_pl = "spadków" if s.direction == "SELL" else "wzrostów"
    side_en = "bearish" if s.direction == "SELL" else "bullish"
    sl_ref_pl = "szczytem retestu" if s.direction == "SELL" else "dołkiem retestu"
    tp_ref_pl = "dołek impulsu" if s.direction == "SELL" else "szczyt impulsu"
    if lang == "pl":
        long = (
            f"{s.break_type} na poziomie {s.level:.2f}, cena wróciła do strefy i została odrzucona. "
            f"Oczekujemy kontynuacji {side_pl}. SL za {sl_ref_pl}, TP na {tp_ref_pl}."
        )
        short = f"{s.break_type} + retest {s.level:.2f}, odrzucenie strefy."
    else:
        long = (
            f"{s.break_type} at {s.level:.2f}, price retested the zone and got rejected. "
            f"Expecting {side_en} continuation. SL beyond the retest swing, TP at the impulse extreme."
        )
        short = f"{s.break_type} + retest of {s.level:.2f}, zone rejected."
    return long, short


SYSTEM_PROMPT = """You write short commentary for a trading-signals channel (gold, XAUUSD).
You receive a detected Smart Money Concepts setup (JSON) and its chart.
Explain in plain words WHY the setup exists: which structure broke (BOS = continuation,
CHOCH = change of character / trend shift), where the zone is, what the retest showed,
why SL and TP sit where they do (both come from market structure).
Rules:
- Do not repeat the entry/SL/TP numbers as a list; they are printed separately.
- No hype, no promises, no "guaranteed". Be factual and brief.
- If the chart shows something that weakens the setup, say it in one short sentence.
- analysis_long: max 3 sentences, max 350 characters.
- analysis_short: max 1 sentence, max 120 characters.
- Write in the language given in the request."""

SCHEMA = {
    "type": "object",
    "properties": {
        "analysis_long": {"type": "string"},
        "analysis_short": {"type": "string"},
    },
    "required": ["analysis_long", "analysis_short"],
    "additionalProperties": False,
}


def ai_analysis(s: Setup, chart: Path, symbol: str, timeframe: str, lang: str,
                model: str) -> tuple[str, str]:
    import anthropic

    client = anthropic.Anthropic()
    image = base64.standard_b64encode(chart.read_bytes()).decode()
    payload = {"symbol": symbol, "timeframe": timeframe, **s.to_dict()}
    response = client.beta.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        # Przy odmowie modelu API samo przełącza się na model zapasowy.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}},
                {"type": "text", "text": f"Language: {lang}\nSetup:\n{json.dumps(payload, default=str)}"},
            ],
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model refused")
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return data["analysis_long"].strip(), data["analysis_short"].strip()


def build_post(s: Setup, chart: Path, symbol: str, timeframe: str, lang: str,
               use_ai: bool, model: str) -> Post:
    long_a, short_a = template_analysis(s, lang)
    if use_ai:
        try:
            long_a, short_a = ai_analysis(s, chart, symbol, timeframe, lang, model)
        except Exception as e:  # brak klucza, sieć, limit — wtedy szablon
            log.warning("AI niedostępne, używam szablonu: %s", e)
    disclaimer = DISCLAIMER.get(lang, DISCLAIMER["en"])
    long = f"{_levels(s, symbol)}\n\n{long_a}\n\n{disclaimer}"
    side = "🔻" if s.direction == "SELL" else "🟢"
    short = (
        f"{symbol} {s.direction} {side} {timeframe}\n"
        f"Entry {s.entry:.2f} | SL {s.sl:.2f} | TP {s.tp:.2f} (RR 1:{s.rr:.1f})\n"
        f"{short_a}\nNFA"
    )
    threads = f"{_levels(s, symbol)}\n\n{short_a}\n\n{disclaimer}"
    return Post(long=long[:1024], threads=threads[:500], short=short[:280])


def result_text(s: Setup, outcome: str, r_multiple: float, symbol: str, lang: str) -> str:
    if outcome == "tp":
        head = "✅ TP"
    elif outcome == "sl":
        head = "❌ SL"
    else:
        head = "⏹ Closed" if lang == "en" else "⏹ Zamknięte"
    return f"{head} — {symbol} {s.direction} @ {s.entry:.2f}: {r_multiple:+.1f}R"
