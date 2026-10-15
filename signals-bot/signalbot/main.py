"""CLI:
    python -m signalbot.main run        # pętla 24/5: sprawdza rynek po zamknięciu każdej świecy
    python -m signalbot.main once       # jedno sprawdzenie (np. z crona)
    python -m signalbot.main backtest   # statystyki strategii na historii
    python -m signalbot.main demo       # wykres + post na danych syntetycznych, bez publikacji
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .chart import render_chart
from .config import Config, load_config
from .data import TF_MINUTES, SyntheticProvider, make_provider
from .publishers import make_publishers
from .strategy import Params, Setup, find_setups
from .tracker import State, evaluate
from .writer import build_post, result_text

log = logging.getLogger("signalbot")


def signal_id(s: Setup) -> str:
    return f"{s.direction}-{pd.Timestamp(s.confirm_time).strftime('%Y%m%d%H%M')}"


def publish_signal(cfg: Config, df: pd.DataFrame, s: Setup, publishers: dict) -> dict:
    sid = signal_id(s)
    chart = render_chart(df, s, cfg.data_dir / "charts" / f"{sid}.png", cfg.display_symbol, cfg.timeframe)
    post = build_post(s, chart, cfg.display_symbol, cfg.timeframe, cfg.language, cfg.use_ai,
                      cfg.anthropic_model)
    ids = {}
    for name, (pub, kind) in publishers.items():
        try:
            ids[name] = pub.publish(getattr(post, kind), chart)
            log.info("Opublikowano %s na %s (%s)", sid, name, ids[name])
        except Exception as e:
            log.error("Błąd publikacji na %s: %s", name, e)
    return {"setup": s.to_dict(), "post_ids": ids, "status": "open", "chart": str(chart)}


def run_once(cfg: Config, provider, state: State, publishers: dict) -> None:
    df = provider.get_bars(cfg.symbol, cfg.timeframe, cfg.bars)
    setups = find_setups(df, Params(min_rr=cfg.min_rr))

    # nowe sygnały: potwierdzone na jednej z 2 ostatnich zamkniętych świec
    for s in setups:
        sid = signal_id(s)
        if s.confirm_idx >= len(df) - 2 and sid not in state.signals:
            log.info("Nowy setup %s %s @ %.2f", sid, s.break_type, s.entry)
            state.signals[sid] = publish_signal(cfg, df, s, publishers)
            state.save()

    # rozliczenie otwartych sygnałów
    for sid, rec in state.signals.items():
        if rec["status"] != "open":
            continue
        st = rec["setup"]
        after = df[df["time"] > pd.Timestamp(st["confirm_time"])]
        res = evaluate(after, st["direction"], st["entry"], st["sl"], st["tp"])
        if res is None:
            continue
        rec.update(status="closed", outcome=res.outcome, r=round(res.r, 2), exit_time=str(res.exit_time))
        text = result_text(Setup(**{**st, "confirm_time": None}), res.outcome, res.r,
                           cfg.display_symbol, cfg.language)
        for name, (pub, _) in publishers.items():
            try:
                pub.publish(text, reply_to=rec["post_ids"].get(name))
            except Exception as e:
                log.error("Błąd publikacji wyniku na %s: %s", name, e)
        log.info("%s zamknięty: %s %+.2fR", sid, res.outcome, res.r)
        state.save()


def run_loop(cfg: Config) -> None:
    provider = make_provider(cfg)
    state = State(cfg.data_dir / "state.json")
    publishers = make_publishers(cfg)
    log.info("Start: %s %s, źródło %s, kanały: %s%s", cfg.symbol, cfg.timeframe, cfg.data_source,
             ", ".join(publishers), " (DRY RUN)" if cfg.dry_run else "")
    step = TF_MINUTES[cfg.timeframe] * 60
    while True:
        try:
            run_once(cfg, provider, state, publishers)
        except Exception:
            log.exception("Błąd w cyklu")
        now = datetime.now(timezone.utc).timestamp()
        time.sleep(step - now % step + 20)  # 20 s po zamknięciu świecy


def backtest(cfg: Config, provider=None, charts: int = 0) -> pd.DataFrame:
    provider = provider or make_provider(cfg)
    df = provider.get_bars(cfg.symbol, cfg.timeframe, cfg.bars)
    rows = []
    for s in find_setups(df, Params(min_rr=cfg.min_rr)):
        res = evaluate(df.iloc[s.confirm_idx + 1 :], s.direction, s.entry, s.sl, s.tp)
        rows.append(dict(time=s.confirm_time, dir=s.direction, type=s.break_type,
                         entry=round(s.entry, 2), sl=round(s.sl, 2), tp=round(s.tp, 2),
                         rr=round(s.rr, 2), outcome=res.outcome if res else "open",
                         r=round(res.r, 2) if res else None))
        if len(rows) <= charts:
            render_chart(df, s, cfg.data_dir / "backtest" / f"{signal_id(s)}.png",
                         cfg.display_symbol, cfg.timeframe)
    out = pd.DataFrame(rows)
    print(out.to_string(index=False) if len(out) else "Brak setupów.")
    closed = out[out["outcome"] != "open"] if len(out) else out
    if len(closed):
        eq = closed["r"].cumsum()
        print(
            f"\nŚwiece: {len(df)}  ({df['time'].iloc[0]:%Y-%m-%d} → {df['time'].iloc[-1]:%Y-%m-%d})"
            f"\nSygnały: {len(closed)}  TP: {(closed.outcome == 'tp').sum()}  "
            f"SL: {(closed.outcome == 'sl').sum()}  timeout: {(closed.outcome == 'timeout').sum()}"
            f"\nWinrate: {(closed.r > 0).mean():.0%}   Suma: {closed.r.sum():+.1f}R   "
            f"Średnio: {closed.r.mean():+.2f}R   Max obsunięcie: {(eq - eq.cummax()).min():.1f}R"
        )
    return out


def demo(cfg: Config) -> None:
    df = SyntheticProvider(seed=1).get_bars(cfg.symbol, cfg.timeframe, 3000)
    s = next(x for x in find_setups(df, Params(min_rr=cfg.min_rr)) if x.direction == "SELL")
    chart = render_chart(df, s, cfg.data_dir / "demo.png", cfg.display_symbol, cfg.timeframe)
    post = build_post(s, chart, cfg.display_symbol, cfg.timeframe, cfg.language, cfg.use_ai,
                      cfg.anthropic_model)
    print(f"Wykres: {chart}\n\n--- Telegram ---\n{post.long}\n\n--- Threads ---\n{post.threads}"
          f"\n\n--- X ---\n{post.short}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="signalbot")
    ap.add_argument("command", choices=["run", "once", "backtest", "demo"])
    ap.add_argument("--env", default=".env")
    ap.add_argument("--charts", type=int, default=0, help="backtest: ile wykresów zapisać")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.env)

    if args.command == "run":
        run_loop(cfg)
    elif args.command == "once":
        run_once(cfg, make_provider(cfg), State(cfg.data_dir / "state.json"), make_publishers(cfg))
    elif args.command == "backtest":
        backtest(cfg, charts=args.charts)
    else:
        demo(cfg)


if __name__ == "__main__":
    main()
