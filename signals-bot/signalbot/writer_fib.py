"""English post copy for zone + Fibonacci signals.

Numbers come from code; the model only writes the "Why" paragraph from the setup context,
so it cannot misquote a level. Without an API key a template paragraph is used.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .fibzone import FibTrade

log = logging.getLogger(__name__)

DISCLAIMER = "⚠️ Not financial advice. Trading leveraged products carries a high level of risk."


@dataclass
class FibPost:
    long: str       # Telegram (photo caption, max 1024 chars)
    threads: str    # Threads (max 500)
    short: str      # X (max 280)
    why_long: str = ""   # explanation, posted as a reply under the signal
    why_short: str = ""


def levels(tr: FibTrade, entry_fib: float = 0.1272) -> dict:
    rng = tr.fib1 - tr.fib0
    lv = lambda f: tr.fib0 + f * rng  # noqa: E731
    entry = lv(entry_fib)
    return {
        "entry": entry,
        "sl": tr.sl,
        "one_r": entry + (entry - tr.sl),
        "tps": [lv(f) for f in tr.tp_fibs],
        "fib0": tr.fib0,
        "fib1": tr.fib1,
    }


def context(tr: FibTrade, trend: dict) -> dict:
    lv = levels(tr)
    return {
        "direction": tr.direction,
        "zone": [round(tr.zone_bot, 2), round(tr.zone_top, 2)],
        "fib_0_reaction_extreme": round(tr.fib0, 2),
        "fib_1_swing": round(tr.fib1, 2),
        "entry_stop_order": round(lv["entry"], 2),
        "stop_loss": round(lv["sl"], 2),
        "one_to_one_rr_price": round(lv["one_r"], 2),
        "zone_on_volume_node_or_poc": tr.vp,
        "volume_poc": round(tr.poc, 2) if tr.poc is not None else None,
    }


def template_why(tr: FibTrade, ctx: dict) -> tuple[str, str]:
    buy = tr.direction == "BUY"
    side = "demand" if buy else "supply"
    move = "drop" if buy else "rally"
    long = (f"Price reached the {side} zone {ctx['zone'][0]:.2f}–{ctx['zone'][1]:.2f} after a {move} from "
            f"{ctx['fib_1_swing']:.2f} and reacted. The stop order at Fib 0.1272 only triggers if the bounce "
            f"is real; the stop sits beyond the reaction extreme (Fib -0.1272).")
    if ctx["zone_on_volume_node_or_poc"]:
        long += " The zone also lines up with a high-volume node."
    short = f"Bounce from the {side} zone + Fib 0.1272 stop entry."
    return long, short


SYSTEM_PROMPT = """You write short, factual commentary for a gold (XAUUSD) trading signals channel.
You get a detected setup as JSON plus its chart. The strategy: price touches an order-block zone,
a Fibonacci is drawn from the reaction extreme (0) to the prior swing (1), a stop order is placed at
Fib 0.1272, stop loss at Fib -0.1272, targets on the following Fibonacci levels.
Explain WHY this setup is on the chart: the zone, the move into it, the reaction, and whether
the zone sits on a volume node / POC. Do not mention trendlines. If something weakens the setup
(e.g. zone in a low-volume area), say it plainly.
Rules: English only. No hype, no promises, no emojis. Do not list entry/SL/TP numbers; they are
printed separately. why_long: max 3 sentences, max 380 characters. why_short: one sentence, max
110 characters."""

SCHEMA = {
    "type": "object",
    "properties": {"why_long": {"type": "string"}, "why_short": {"type": "string"}},
    "required": ["why_long", "why_short"],
    "additionalProperties": False,
}


def ai_why(ctx: dict, chart: Path, symbol: str, timeframe: str, model: str) -> tuple[str, str]:
    import anthropic

    client = anthropic.Anthropic()
    image = base64.standard_b64encode(chart.read_bytes()).decode()
    response = client.beta.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}},
            {"type": "text", "text": f"{symbol} {timeframe}\n{json.dumps(ctx)}"},
        ]}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model refused")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    return data["why_long"].strip(), data["why_short"].strip()


def build_fib_post(tr: FibTrade, chart: Path, ctx: dict, symbol: str, timeframe: str,
                   use_ai: bool, model: str, invite_url: str = "") -> FibPost:
    why_long, why_short = template_why(tr, ctx)
    if use_ai:
        try:
            why_long, why_short = ai_why(ctx, chart, symbol, timeframe, model)
        except Exception as e:  # no key, network, rate limit -> template
            log.warning("AI unavailable, using template: %s", e)
    lv = levels(tr)
    icon = "🟢" if tr.direction == "BUY" else "🔴"
    tps = " · ".join(f"TP{i + 1} {p:.2f}" for i, p in enumerate(lv["tps"]))
    head = f"{symbol} {tr.direction} {icon} | {timeframe}"
    invite = f"\n\n📲 Live updates & results on Telegram: {invite_url}" if invite_url else ""
    long = (
        f"{head}\n\n"
        f"📍 Entry: {lv['entry']:.2f}\n"
        f"🛑 Stop loss: {lv['sl']:.2f}\n"
        f"🎯 {tps}\n\n"
        f"⚙️ Take partials at each TP, stop to breakeven after TP1.\n\n"
        f"{DISCLAIMER}"
    )
    threads = (
        f"{head}\n"
        f"Entry {lv['entry']:.2f} | SL {lv['sl']:.2f} | TP {lv['tps'][0]:.2f} → {lv['tps'][-1]:.2f}"
        f"{invite}\n\nNot financial advice."
    )
    short = (
        f"{head}\n"
        f"Entry {lv['entry']:.2f} | SL {lv['sl']:.2f}\n"
        f"TP1 {lv['tps'][0]:.2f} … TP{len(lv['tps'])} {lv['tps'][-1]:.2f}"
        + (f"\n👉 {invite_url}" if invite_url else "") + "\nNFA"
    )
    return FibPost(long=long[:1024], threads=threads[:500], short=short[:280],
                   why_long=f"🧭 {why_long}", why_short=f"🧭 {why_short}")


def update_text(tr: FibTrade, symbol: str) -> str:
    lv = levels(tr)
    tps = " · ".join(f"TP{i + 1} {p:.2f}" for i, p in enumerate(lv["tps"]))
    return (f"🔄 {symbol} {tr.direction} update — new levels:\n"
            f"📍 Entry: {lv['entry']:.2f}\n🛑 Stop loss: {lv['sl']:.2f}\n🎯 {tps}")


def cancel_text(direction: str, symbol: str) -> str:
    return f"❌ {symbol} {direction}: entry was not triggered — setup cancelled, remove the pending order."


def pips(direction: str, entry: float, price: float, pip_size: float) -> float:
    """Wynik w pipsach od ceny wejścia z sygnału (dodatni = zysk)."""
    move = price - entry if direction == "BUY" else entry - price
    return move / pip_size


def exit_text(tr: FibTrade, name: str, price: float, entry: float, pip_size: float, symbol: str) -> str:
    """Odpowiedź pod sygnałem po TP / SL / zamknięciu."""
    p = pips(tr.direction, entry, price, pip_size)
    if name.startswith("tp"):
        k = int(name[2:])
        extra = "\nStop to breakeven 🔒" if k == 1 else ""
        return f"🎯 {symbol} {tr.direction} TP{k} hit @ {price:.2f}\n💰 +{p:.0f} pips 💪{extra}"
    if name == "sl" and abs(p) < 0.5:
        return f"🔒 {symbol} {tr.direction} closed at breakeven @ {price:.2f} — 0 pips"
    if name == "sl":
        return f"🛑 {symbol} {tr.direction} SL hit @ {price:.2f}\n📉 {p:.0f} pips"
    return f"⏹ {symbol} {tr.direction} closed @ {price:.2f} — {p:+.0f} pips"


def one_r_text(tr: FibTrade, price: float, symbol: str) -> str:
    return (f"✅ {symbol} {tr.direction}: 1:1 RR secured.\n"
            f"Stop to breakeven and let the rest run to the next targets.")


def final_text(tr: FibTrade, r: float, tps_hit: int, symbol: str) -> str:
    return f"🏁 {symbol} {tr.direction} closed: {tps_hit}/{len(tr.tp_fibs)} targets hit, +{r:.1f}R on the trade."
