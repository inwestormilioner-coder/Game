"""Porównanie wariantów strategii Liquidity + FVG + BOS (i obecnej fibzone).

    python -m signalbot.ictcompare XAUUSD_M15.csv --tf M15
"""
from __future__ import annotations

import argparse

import pandas as pd

from .compare import stats
from .data import CSVProvider
from .fibzone import SIGNAL_TPS, FibParams, find_fib_trades
from .ict import IctFibParams, IctParams, find_ict_trades, find_ictfib_trades

VARIANTS = {
    "ICT pełny: liq+BOS+FVG, wejście góra FVG, TP płynność": IctParams(),
    "ICT: wejście 50% FVG": IctParams(entry="mid"),
    "ICT: TP 2R": IctParams(tp_mode="rr", rr=2.0),
    "ICT: TP 3R": IctParams(tp_mode="rr", rr=3.0),
    "ICT: bez wymogu płynności": IctParams(require_liq=False),
    "ICT: bez wymogu BOS": IctParams(require_bos=False),
    "ICT: SL za lokalnym dołkiem/szczytem": IctParams(sl_mode="swing"),
    "ICT: SL za swingiem, min RR 1.0": IctParams(sl_mode="swing", min_rr=1.0),
    "ICT: SL za swingiem, TP 2R": IctParams(sl_mode="swing", tp_mode="rr", rr=2.0),
    "ICT limit + SL swing + TP Fibo impulsu (1/1.272/1.618)": IctParams(sl_mode="swing", tp_mode="fibext"),
    "ICT limit + SL za FVG + TP Fibo impulsu": IctParams(tp_mode="fibext"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--spread", type=float, default=0.30)
    ap.add_argument("--max-hold", type=int, default=192)
    ap.add_argument("--min-risk", type=float, default=3.0)
    args = ap.parse_args()
    df = CSVProvider(args.csv).get_bars("XAUUSD", args.tf)
    mid = df["time"].iloc[len(df) // 2]
    print(f"{args.tf}: {len(df)} świec, {df['time'].iloc[0]:%Y-%m-%d} → {df['time'].iloc[-1]:%Y-%m-%d}, "
          f"spread ${args.spread}, min SL ${args.min_risk}\n")
    rows = []

    def add(name, items):
        t = pd.DataFrame(items, columns=["time", "r"])
        full, a, b = stats(t), stats(t[t.time < mid]), stats(t[t.time >= mid])
        rows.append({"wariant": name, **full, "1.poł R": a["sumR"], "2.poł R": b["sumR"]})

    for name, p in VARIANTS.items():
        p.max_hold, p.min_risk = args.max_hold, args.min_risk
        tr = [x for x in find_ict_trades(df, p) if x.closed]
        add(name, [(df["time"].iloc[x.entry_idx], x.r - args.spread / abs(x.entry - x.sl)) for x in tr])

    hyb = {
        "HYBRYDA ICT+Fibo: stop 0.1272, SL -0.1272, 5 TP, BE po TP1": IctFibParams(),
        "HYBRYDA: SL za lokalnym swingiem": IctFibParams(sl_mode="swing"),
        "HYBRYDA: 1 TP na 1.0": IctFibParams(tps=(1.0,), fractions=(1.0,), be_after=None),
        "HYBRYDA: 1 TP na 1.272": IctFibParams(tps=(1.272,), fractions=(1.0,), be_after=None),
        "HYBRYDA: SL swing, 1 TP na 1.272": IctFibParams(sl_mode="swing", tps=(1.272,), fractions=(1.0,),
                                                         be_after=None),
    }
    for name, q in hyb.items():
        q.ict.max_hold, q.ict.min_risk = args.max_hold, args.min_risk
        tr = [x for x in find_ictfib_trades(df, q) if x.closed]
        add(name, [(df["time"].iloc[x.entry_idx], x.r - args.spread / abs(x.entry - x.sl)) for x in tr])

    fp = FibParams(tps=SIGNAL_TPS, fractions=(0.2,) * 5, be_after=0, max_hold=args.max_hold, min_risk=args.min_risk)
    tr = [x for x in find_fib_trades(df, fp) if x.closed]
    add("OBECNA fibzone (5 TP, BE po TP1)", [(df["time"].iloc[x.entry_idx], x.r - args.spread / x.risk) for x in tr])
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
