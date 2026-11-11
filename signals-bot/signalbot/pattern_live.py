"""Bot formacji na żywo - łańcuch agentów:

  Skaner (kod: ZigZag ATR + formacje)  ->  Konfluencje (strefy M15/H1, Wasze strefy, Fibo, VP, struktura H1)
  ->  Wykres  ->  Analityk AI (czy publikować)  ->  Autor AI (akapit "Why")
  ->  Publikacja (Telegram / Threads / X)  ->  Śledzenie (odpowiedzi pod postem po TP / SL)

Stan w data/patterns_state.json, osobno od sygnałów strategii.
"""
from __future__ import annotations

import logging
from dataclasses import fields

import pandas as pd

from .chart_pattern import render_pattern_chart
from .config import Config
from .pattern_ai import Verdict, analyst_verdict, pattern_context, writer_why
from .patterns import ALL_KINDS, HARMONIC_KINDS, Pattern, PatternParams, find_patterns, load_user_zones, simulate
from .tracker import State
from .writer_fib import DISCLAIMER, pips

log = logging.getLogger("signalbot")


def pattern_params(cfg: Config) -> PatternParams:
    kinds = ALL_KINDS
    if cfg.pattern_kinds and cfg.pattern_kinds != "all":
        sel = [k.strip() for k in cfg.pattern_kinds.split(",") if k.strip()]
        kinds = tuple(k for k in ALL_KINDS if k in sel or (k in HARMONIC_KINDS and "harmonic" in sel)
                      or (k not in HARMONIC_KINDS and "chart" in sel))
    return PatternParams(depths=cfg.pattern_depths, kinds=kinds)


# ----------------------------------------------------------------------------- teksty postów

def _head(pt: Pattern, symbol: str, timeframe: str) -> str:
    icon = "🟢" if pt.direction == "BUY" else "🔴"
    return f"{symbol} {pt.name} {icon} {pt.direction} | {timeframe}"


def build_pattern_post(pt: Pattern, why: tuple[str, str], verdict: Verdict | None, symbol: str,
                       timeframe: str) -> dict:
    head = _head(pt, symbol, timeframe)
    tps = " · ".join(f"TP{i + 1} {x:.2f}" for i, x in enumerate(pt.tps))
    if pt.family == "harmonic":
        setup = f"🧩 D completed in the PRZ {pt.prz[0]:.2f}–{pt.prz[1]:.2f} and got rejected."
    elif "wedge" in pt.kind:
        side, line = ("below", "wedge support") if pt.direction == "SELL" else ("above", "wedge resistance")
        ctx = {"reversal": "reversal after the move into it",
               "continuation": "the prior trend resumes"}.get(pt.details.get("context"), "")
        setup = (f"🧩 Candle closed {side} the {line} {pt.details.get('neckline_break', 0):.2f}"
                 + (f" ({ctx})." if ctx else "."))
    else:
        side = "below" if pt.direction == "SELL" else "above"
        setup = f"🧩 Candle closed {side} the neckline {pt.details.get('neckline_break', 0):.2f}."
    conf = "\n".join(f"• {c}" for c in pt.confluences) if pt.confluences else "• none"
    grade = f"\n🤖 AI review: grade {verdict.grade} ({verdict.confidence}%)" if verdict else ""
    long = (f"{head}\n\n{setup}\n\n📍 Entry: {pt.entry:.2f}\n🛑 Stop loss: {pt.sl:.2f}\n🎯 {tps}\n\n"
            f"✅ Confluence ({pt.score}):\n{conf}{grade}\n\n"
            f"⚙️ Half at TP1, stop to breakeven, rest to TP{len(pt.tps)}.\n\n{DISCLAIMER}")
    short_conf = ", ".join(pt.confluences[:2])
    threads = (f"{head}\nEntry {pt.entry:.2f} | SL {pt.sl:.2f} | {tps}\n"
               f"Confluence: {', '.join(pt.confluences) or 'none'}"
               f"\n\n📲 Do you wanna join for free? Check my profile for the link.\n\nNot financial advice.")
    short = (f"{head}\nEntry {pt.entry:.2f} | SL {pt.sl:.2f}\n{tps}"
             + (f"\nConfluence: {short_conf}" if short_conf else "")
             + "\n📲 Join for free, link in my profile.\nNFA")
    return {"long": long[:1024], "threads": threads[:500], "short": short[:280],
            "why_long": f"🧭 {why[0]}", "why_short": f"🧭 {why[1]}"}


def exit_reply(pt: Pattern, name: str, price: float, pip_size: float, symbol: str) -> str:
    p = pips(pt.direction, pt.entry, price, pip_size)
    if name.startswith("tp"):
        k = int(name[2:])
        extra = "\nStop to breakeven 🔒" if k < len(pt.tps) else "\n🏁 Pattern target reached."
        return f"🎯 {symbol} {pt.name} TP{k} hit @ {price:.2f}\n💰 +{p:.0f} pips 💪{extra}"
    if name == "be":
        return f"🔒 {symbol} {pt.name}: rest closed at breakeven @ {price:.2f}."
    if name == "sl":
        return f"🛑 {symbol} {pt.name} SL hit @ {price:.2f}\n📉 {p:.0f} pips"
    return f"⏹ {symbol} {pt.name} closed @ {price:.2f} — {p:+.0f} pips"


# ----------------------------------------------------------------------------- obieg

def _publish(publishers: dict, texts: dict, chart, reply_to: dict | None = None) -> dict:
    ids = {}
    for name, (pub, kind) in publishers.items():
        try:
            if reply_to is not None:
                if reply_to.get(name):
                    ids[name] = pub.publish(texts[kind], reply_to=reply_to[name])
                continue
            ids[name] = pub.publish(texts[kind], chart)
            pub.publish(texts["why_long"] if kind == "long" else texts["why_short"], reply_to=ids[name])
        except Exception as e:  # noqa: BLE001
            log.error("Formacje: publikacja na %s nie wyszła: %s", name, e)
    return ids


def process_pattern(cfg: Config, df: pd.DataFrame, pt: Pattern, publishers: dict) -> dict:
    """Jeden sygnał przez cały łańcuch agentów. Zwraca rekord do stanu."""
    rec = {"pattern": {f.name: getattr(pt, f.name) for f in fields(Pattern)}, "id": pt.id, "name": pt.name,
           "status": "skipped", "post_ids": {}, "sent": []}
    if pt.score < cfg.pattern_min_score:
        rec["reason"] = f"score {pt.score} < {cfg.pattern_min_score}"
        log.info("Formacja %s pominięta: %s", pt.id, rec["reason"])
        return rec
    chart = render_pattern_chart(df, pt, cfg.data_dir / "charts" / f"{pt.id}.png", cfg.display_symbol,
                                 cfg.timeframe, handle=cfg.handle, source=cfg.chart_source)
    ctx = pattern_context(df, pt, cfg.display_symbol, cfg.timeframe)
    verdict = None
    if cfg.pattern_ai_filter and cfg.use_ai:
        verdict = analyst_verdict(ctx, chart, cfg.anthropic_model)
        if verdict is not None:
            rec["ai"] = verdict.__dict__
            if not verdict.take or verdict.confidence < cfg.pattern_min_confidence:
                rec["reason"] = f"AI: {verdict.reason}"
                log.info("Formacja %s odrzucona przez AI (%s, %d%%): %s", pt.id, verdict.grade,
                         verdict.confidence, verdict.reason)
                return rec
    why = writer_why(ctx, pt, chart, cfg.anthropic_model, cfg.use_ai)
    texts = build_pattern_post(pt, why, verdict, cfg.display_symbol, cfg.timeframe)
    rec["post_ids"] = _publish(publishers, texts, chart)
    rec.update(status="open", chart=str(chart))
    log.info("Formacja %s opublikowana (score %d)", pt.id, pt.score)
    return rec


def track(cfg: Config, df: pd.DataFrame, state: State, publishers: dict) -> None:
    """Odpowiedzi pod postem formacji: TP, breakeven, SL (gdy REPLY_LOSSES), zamknięcie po czasie."""
    for sid, rec in state.signals.items():
        if rec.get("status") != "open":
            continue
        pt = Pattern(**rec["pattern"])
        t0 = pd.Timestamp(pt.confirm_time)
        d = df[df["time"] >= t0].reset_index(drop=True)
        if d.empty or d["time"].iloc[0] != t0:
            continue                             # świeca potwierdzenia wypadła z okna danych
        pt.confirm_idx = 0
        simulate(d, pt)
        for name, _, price in pt.exits:
            key = f"{name}@{price:.2f}"
            if key in rec["sent"]:
                continue
            rec["sent"].append(key)
            if name == "sl" and not cfg.reply_losses:
                continue
            text = exit_reply(pt, name, price, cfg.pip_size, cfg.display_symbol)
            _publish(publishers, {k: text for k in ("long", "threads", "short")}, None, reply_to=rec["post_ids"])
        if pt.outcome != "open":
            rec.update(status="closed", outcome=pt.outcome, r=round(pt.r, 2))
            log.info("Formacja %s zamknięta: %s %+.2fR", sid, pt.outcome, pt.r)
        state.save()


def run_once_patterns(cfg: Config, df: pd.DataFrame, state: State, publishers: dict) -> None:
    pats = find_patterns(df, pattern_params(cfg), load_user_zones(cfg.zones_file))
    for pt in pats:
        # tylko formacje potwierdzone na jednej z 2 ostatnich zamkniętych świec
        if pt.confirm_idx < len(df) - 2 or pt.id in state.signals:
            continue
        log.info("Nowa formacja %s (%s, score %d)", pt.id, pt.name, pt.score)
        state.signals[pt.id] = process_pattern(cfg, df, pt, publishers)
        state.save()
    track(cfg, df, state, publishers)
