"""Live loop for the zone + Fibonacci strategy: post new signals, reply once 1:1 RR is reached."""
from __future__ import annotations

import logging

import pandas as pd

from .chart_fib import _trendline
from .chart_tv import render_post_chart
from .config import Config
from .fibzone import FibParams, FibTrade, find_fib_trades, scan_live
from .tracker import State
from .writer_fib import build_fib_post, cancel_text, context, final_text, levels, one_r_text, update_text

log = logging.getLogger("signalbot")


def fib_params(cfg: Config) -> FibParams:
    tps = cfg.tp_levels
    return FibParams(tps=tps, fractions=tuple(1 / len(tps) for _ in tps), be_after=0, min_risk=cfg.min_sl,
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
    chart = render_post_chart(df, tr, cfg.data_dir / "charts" / f"{sid}.png", cfg.display_symbol,
                              cfg.timeframe, handle=cfg.handle, source=cfg.chart_source)
    ctx = context(tr, trend_info(df, tr.entry_idx))
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


def _reply(publishers: dict, rec: dict, text: str) -> None:
    for name, (pub, _) in publishers.items():
        try:
            pub.publish(text, reply_to=rec["post_ids"].get(name))
        except Exception as e:
            log.error("Reply on %s failed: %s", name, e)


def run_once_fib(cfg: Config, df: pd.DataFrame, state: State, publishers: dict, only: str | None = None) -> None:
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
            state.save()
        elif rec["status"] == "pending" and abs(rec["levels"]["entry"] - lv["entry"]) >= \
                0.25 * abs(rec["levels"]["entry"] - rec["levels"]["sl"]):
            # nowy dołek/szczyt w strefie przesunął Fibo -> aktualizacja poziomów
            _reply(publishers, rec, update_text(pd_tr, cfg.display_symbol))
            rec["levels"] = {k: v for k, v in lv.items() if k != "tps"}
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
            rec["status"] = "cancelled"
            log.info("%s cancelled", sid)
        state.save()

    for tr in trades:
        rec = state.signals.get(tr.id)
        if rec is None or rec["status"] != "open":
            continue
        if not rec["one_r_sent"]:
            price = _reached_one_r(df, tr)
            if price is not None:
                _reply(publishers, rec, one_r_text(tr, price, cfg.display_symbol))
                rec["one_r_sent"] = True
                state.save()
        if tr.closed:
            tps_hit = sum(1 for e in tr.exits if e[0].startswith("tp"))
            rec.update(status="closed", r=round(tr.r, 2), tps_hit=tps_hit)
            if rec["one_r_sent"] and tr.r >= 1.0:
                _reply(publishers, rec, final_text(tr, tr.r, tps_hit, cfg.display_symbol))
            elif cfg.reply_losses:
                _reply(publishers, rec, f"{cfg.display_symbol} {tr.direction} closed: {tr.r:+.1f}R.")
            log.info("%s closed: %+.2fR, %d TPs", tr.id, tr.r, tps_hit)
            state.save()


def live_replay(cfg: Config, df: pd.DataFrame, tr: FibTrade, publishers: dict, state: State) -> None:
    """Test: feed bars one by one from the zone touch until the trade closes, like the live bot would see them."""
    end = tr.exits[-1][1] if tr.exits else tr.entry_idx
    for i in range(tr.touch_idx, end + 1):
        run_once_fib(cfg, df.iloc[: i + 1].reset_index(drop=True), state, publishers, only=tr.id)
