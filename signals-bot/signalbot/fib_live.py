"""Live loop for the zone + Fibonacci strategy: post new signals, reply once 1:1 RR is reached."""
from __future__ import annotations

import logging
import os

import pandas as pd

from .chart_fib import _trendline
from .chart_tv import render_post_chart
from .config import Config
from .fibzone import FibParams, FibTrade, find_fib_trades, scan_live
from .tracker import State
from .summary import book_exit, due_summaries, summary_text
from .structure import find_swings
from .writer_fib import (ai_close_text, ai_move_text, ai_partial_text, ai_stop_text, build_fib_post, cancel_text,
                         context, exit_text, levels, pips, rev_text, update_text)

log = logging.getLogger("signalbot")


def fib_params(cfg: Config) -> FibParams:
    tps = cfg.tp_levels
    return FibParams(tps=tps, fractions=tuple(1 / len(tps) for _ in tps), be_after=0, min_risk=cfg.min_sl,
                     rev_exit=cfg.ai_exit and not manager_active(cfg), rev_min_r=cfg.ai_exit_min_r,
                     max_hold=4 * 24 * 60 // _tf_minutes(cfg.timeframe) // 2)  # ~2 days


def _tf_minutes(tf: str) -> int:
    from .data import TF_MINUTES

    return TF_MINUTES[tf]


def trend_info(df: pd.DataFrame, end: int, short: int = 30, long: int = 100) -> dict:
    if end - long < 0:
        return {}
    out = {}
    for name, vals, lowest in (("support", df["low"].to_numpy(), True), ("resistance", df["high"].to_numpy(), False)):
        x1, y1, x2, y2 = _trendline(vals, end, short, long, lowest)
        out[name] = "rising" if y2 > y1 else "falling"
    return out


def _reached_one_r(df: pd.DataFrame, tr: FibTrade) -> float | None:
    """Price at which 1:1 RR was first reached after entry, or None (also None if SL came first)."""
    lv = levels(tr)
    after = df.iloc[tr.entry_idx + 1 :]
    for row in after.itertuples(index=False):
        if tr.direction == "BUY":
            if row.low <= lv["sl"]:
                return None
            if row.high >= lv["one_r"]:
                return lv["one_r"]
        else:
            if row.high >= lv["sl"]:
                return None
            if row.low <= lv["one_r"]:
                return lv["one_r"]
    return None


def publish_fib(cfg: Config, df: pd.DataFrame, tr: FibTrade, publishers: dict) -> dict:
    sid = tr.id.replace(":", "").replace(" ", "_").replace("+0000", "")
    chart_path = cfg.data_dir / "charts" / f"{sid}.png"
    chart = None
    if cfg.chart_mode == "tradingview":
        from .tvshot import capture_for

        chart = capture_for(cfg, chart_path)
    if chart is None:
        chart = render_post_chart(df, tr, chart_path, cfg.display_symbol,
                                  cfg.timeframe, handle=cfg.handle, source=cfg.chart_source)
    ctx = context(tr, {})
    post = build_fib_post(tr, chart, ctx, cfg.display_symbol, cfg.timeframe, cfg.use_ai, cfg.anthropic_model,
                          cfg.invite_url)
    kinds = {"long": post.long, "threads": post.threads, "short": post.short}
    ids = {}
    for name, (pub, kind) in publishers.items():
        try:
            ids[name] = pub.publish(kinds[kind], chart)
            log.info("Posted %s to %s (%s)", tr.id, name, ids[name])
            # explanation goes as a reply under the signal
            pub.publish(post.why_long if kind == "long" else post.why_short, reply_to=ids[name])
        except Exception as e:
            log.error("Publishing to %s failed: %s", name, e)
    return {"id": tr.id, "direction": tr.direction, "post_ids": ids, "status": "open", "chart": str(chart),
            "levels": {k: v for k, v in levels(tr).items() if k != "tps"}, "one_r_sent": False}


def manager_active(cfg: Config) -> bool:
    """AI-menedżer działa, gdy jest włączony i jest klucz API; inaczej zostaje prosta reguła AI_EXIT."""
    return cfg.ai_manager and cfg.use_ai and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _ai_stop_hit(df: pd.DataFrame, direction: str, ai: dict) -> int | None:
    """Indeks świecy, w której cena dotknęła SL ustawionego przez AI (świece po decyzji)."""
    if ai.get("sl") is None:
        return None
    after = df.index[df["time"] > pd.Timestamp(ai["sl_bar"])]
    for i in after:
        if (direction == "BUY" and df["low"].iloc[i] <= ai["sl"]) or \
                (direction == "SELL" and df["high"].iloc[i] >= ai["sl"]):
            return int(i)
    return None


def manage_with_ai(cfg: Config, df: pd.DataFrame, tr: FibTrade, rec: dict, entry: float, publishers: dict,
                   trader) -> None:
    """Raz na świecę: AI ocenia strukturę rynku i trzyma / przesuwa SL / realizuje część / zamyka."""
    from .ai_manager import decide

    ai = rec.setdefault("ai", {})
    bar = str(df["time"].iloc[-1])
    if ai.get("last_bar") == bar:
        return
    ai["last_bar"] = bar
    price = float(df["close"].iloc[-1])
    buy = tr.direction == "BUY"
    risk = abs(entry - tr.sl)
    profit_r = ((price - entry) if buy else (entry - price)) / risk
    if not rec.get("tp_hit") and profit_r < cfg.ai_manager_min_r:
        return                                   # AI zarządza dopiero pozycją na zysku
    sent = tr.exits[: rec.get("exits_sent", 0)]
    k = sum(1 for e in sent if e[0].startswith("tp"))
    left = (1 - sum(e[3] for e in sent if e[0].startswith("tp"))) * ai.get("left_mult", 1.0)
    cur_sl = ai.get("sl", entry if k else tr.sl)
    rec["tps_left"] = levels(tr)["tps"][k:]
    d = decide(cfg, df, tr, rec, cur_sl, left, entry)
    sym, when = cfg.display_symbol, df["time"].iloc[-1]
    p_now = pips(tr.direction, entry, price, cfg.pip_size)
    if d.action == "move_sl":
        ai.update(sl=float(d.new_sl), sl_bar=bar)
        _reply(publishers, rec, ai_move_text(tr, d.new_sl, pips(tr.direction, entry, d.new_sl, cfg.pip_size),
                                             d.reason, sym))
        _trade(trader, "move_sl", rec, float(d.new_sl))
    elif d.action == "partial":
        ai["left_mult"] = ai.get("left_mult", 1.0) * (1 - d.close_pct / 100)
        book_exit(rec, "ai_partial", p_now, when)
        _reply(publishers, rec, ai_partial_text(tr, price, d.close_pct, p_now, d.reason, sym))
        _trade(trader, "partial", rec, d.close_pct)
    elif d.action == "close":
        book_exit(rec, "ai_close", p_now, when)
        _reply(publishers, rec, ai_close_text(tr, price, rec["pips"], d.reason, sym))
        _trade(trader, "close_all", rec)
        rec.update(status="closed", tps_hit=rec.get("tp_hit", 0))
        log.info("%s closed by AI @ %.2f", tr.id, price)


def reversal_level(df: pd.DataFrame, tr: FibTrade, idx: int, n: int = 3) -> float | None:
    """Swing złamany przy wyjściu AI: dla BUY ostatni swing low po wejściu, dla SELL swing high."""
    highs, lows = find_swings(df.iloc[: idx + 1], n)
    sw = [s for s in (lows if tr.direction == "BUY" else highs) if s.idx > tr.entry_idx and s.confirmed_at <= idx]
    return sw[-1].price if sw else None


def _reply(publishers: dict, rec: dict, text: str) -> None:
    for name, (pub, _) in publishers.items():
        try:
            pub.publish(text, reply_to=rec["post_ids"].get(name))
        except Exception as e:
            log.error("Reply on %s failed: %s", name, e)


def _trade(trader, action: str, *args) -> None:
    """Błąd po stronie brokera nie może zatrzymać publikacji sygnałów."""
    if trader is None:
        return
    try:
        getattr(trader, action)(*args)
    except Exception as e:
        log.error("Auto-trading (%s) nieudany: %s", action, e)


def run_once_fib(cfg: Config, df: pd.DataFrame, state: State, publishers: dict, only: str | None = None,
                 trader=None) -> None:
    trades, pending = scan_live(df, fib_params(cfg))
    by_id = {t.id: t for t in trades}
    last = df.iloc[-1]
    live_n = sum(1 for r in state.signals.values() if r["status"] in ("pending", "open"))
    log.info("Checked %s candle %s close %.2f | active signals: %d", cfg.timeframe,
             pd.Timestamp(last["time"]).strftime("%Y-%m-%d %H:%M"), last["close"], live_n)

    # 1) zlecenie oczekujące: publikujemy ZANIM cena dojdzie do wejścia
    pend_ids = set()
    for pd_tr in pending:
        pend_ids.add(pd_tr.id)
        if only not in (None, pd_tr.id):
            continue
        rec = state.signals.get(pd_tr.id)
        lv = levels(pd_tr)
        late = last["close"] >= lv["entry"] if pd_tr.direction == "BUY" else last["close"] <= lv["entry"]
        if rec is None and late:
            continue  # cena już za wejściem - nie wysyłamy spóźnionego sygnału, czekamy na lepszy moment
        if rec is None:
            log.info("New pending %s %s @ %.2f", pd_tr.direction, pd_tr.id, lv["entry"])
            rec = publish_fib(cfg, df, pd_tr, publishers)
            rec["status"] = "pending"
            state.signals[pd_tr.id] = rec
            _trade(trader, "place", rec, pd_tr.direction, lv["entry"], lv["sl"], lv["tps"])
            state.save()
        elif rec["status"] == "pending" and abs(rec["levels"]["entry"] - lv["entry"]) >= \
                0.25 * abs(rec["levels"]["entry"] - rec["levels"]["sl"]):
            # nowy dołek/szczyt w strefie przesunął Fibo -> aktualizacja poziomów
            _reply(publishers, rec, update_text(pd_tr, cfg.display_symbol))
            rec["levels"] = {k: v for k, v in lv.items() if k != "tps"}
            _trade(trader, "update", rec, lv["entry"], lv["sl"], lv["tps"])
            rec["mt5_entry"] = lv["entry"]
            state.save()
        elif rec["status"] == "pending" and trader is not None and \
                abs(rec.get("mt5_entry", rec["levels"]["entry"]) - lv["entry"]) >= 0.01:
            # małe przesunięcie (bez posta) - zlecenia na MT5 i tak idą za poziomami bota
            _trade(trader, "update", rec, lv["entry"], lv["sl"], lv["tps"])
            rec["mt5_entry"] = lv["entry"]
            state.save()

    # 2) oczekujące, które zniknęły: aktywowane (są w transakcjach) albo anulowane
    for sid, rec in state.signals.items():
        if rec["status"] != "pending" or sid in pend_ids:
            continue
        if sid in by_id:
            rec["status"] = "open"
            log.info("%s triggered @ %.2f", sid, by_id[sid].entry)
        else:
            _reply(publishers, rec, cancel_text(rec["direction"], cfg.display_symbol))
            _trade(trader, "cancel", rec)
            rec["status"] = "cancelled"
            log.info("%s cancelled", sid)
        state.save()

    for tr in trades:
        rec = state.signals.get(tr.id)
        if rec is None or rec["status"] != "open":
            continue
        # każde nowe wyjście (TP1..TPn, SL, zamknięcie) -> odpowiedź z pipsami od ceny wejścia z sygnału
        entry = rec.get("levels", {}).get("entry", levels(tr)["entry"])
        sent = rec.setdefault("exits_sent", 0)
        ai = rec.get("ai", {})
        stop_idx = _ai_stop_hit(df, tr.direction, ai)
        new_exits = [e for e in tr.exits[sent:] if stop_idx is None or e[1] < stop_idx]
        for name, idx, price, _ in new_exits:
            after_tp = bool(rec.get("tp_hit"))
            book_exit(rec, name, pips(tr.direction, entry, price, cfg.pip_size), df["time"].iloc[idx])
            if name == "rev":
                _reply(publishers, rec, rev_text(tr, price, rec["pips"], reversal_level(df, tr, idx),
                                                 cfg.timeframe, cfg.display_symbol))
            # po TP nie informujemy o zamknięciu reszty (BE / czas) - każdy zarządza pozycją po swojemu
            elif not (after_tp and not name.startswith("tp")):
                _reply(publishers, rec, exit_text(tr, name, price, entry, cfg.pip_size, cfg.display_symbol))
            log.info("%s %s @ %.2f", tr.id, name, price)
            if name == "tp1":
                _trade(trader, "breakeven", rec)
            elif name in ("timeout", "rev"):
                _trade(trader, "close_all", rec)
        if new_exits:
            rec["exits_sent"] = sent + len(new_exits)
            state.save()
        if stop_idx is not None:
            # stop przesunięty przez AI został trafiony
            book_exit(rec, "ai_sl", pips(tr.direction, entry, ai["sl"], cfg.pip_size), df["time"].iloc[stop_idx])
            _reply(publishers, rec, ai_stop_text(tr, ai["sl"], rec["pips"], cfg.display_symbol))
            _trade(trader, "close_all", rec)
            rec.update(status="closed", tps_hit=rec.get("tp_hit", 0))
            log.info("%s AI stop hit @ %.2f", tr.id, ai["sl"])
            state.save()
        elif tr.closed and rec["exits_sent"] >= len(tr.exits):
            tps_hit = sum(1 for e in tr.exits if e[0].startswith("tp"))
            rec.update(status="closed", r=round(tr.r, 2), tps_hit=tps_hit)
            log.info("%s closed: %+.2fR, %d TPs", tr.id, tr.r, tps_hit)
            state.save()
        elif manager_active(cfg):
            manage_with_ai(cfg, df, tr, rec, entry, publishers, trader)
            state.save()

    if only is None:
        post_summaries(cfg, state, publishers, last["time"] + pd.Timedelta(minutes=_tf_minutes(cfg.timeframe)))


def post_summaries(cfg: Config, state: State, publishers: dict, now: pd.Timestamp) -> None:
    """Podsumowanie dnia (pn–pt) i tygodnia (piątek) w pipsach, jako osobny post na wszystkich kanałach."""
    meta = state.data.setdefault("meta", {})
    for kind, start, end in due_summaries(meta, pd.Timestamp(now), cfg.summary_hour_utc):
        text = summary_text(state.signals, start, end, cfg.display_symbol, weekly=kind == "weekly")
        if text:
            for name, (pub, _) in publishers.items():
                try:
                    pub.publish(text)
                except Exception as e:
                    log.error("%s summary on %s failed: %s", kind, name, e)
            log.info("Posted %s summary", kind)
        meta[f"{kind}_at"] = end.isoformat()
        state.save()


def live_replay(cfg: Config, df: pd.DataFrame, tr: FibTrade, publishers: dict, state: State) -> None:
    """Test: feed bars one by one from the zone touch until the trade closes, like the live bot would see them."""
    end = tr.exits[-1][1] if tr.exits else tr.entry_idx
    for i in range(tr.touch_idx, end + 1):
        run_once_fib(cfg, df.iloc[: i + 1].reset_index(drop=True), state, publishers, only=tr.id)
