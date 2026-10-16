"""Porównanie wariantów strategii "odbicie od strefy + Fibo".

    python -m signalbot.fibcompare data/XAUUSD_15m.csv --tf M15
"""
from __future__ import annotations

import argparse

import pandas as pd

from .compare import stats
from .data import CSVProvider
from .fibzone import FIB_TPS, FibParams, find_fib_trades

ALL9 = tuple(1 / 9 for _ in FIB_TPS)

VARIANTS = {
    "TP 0.382": FibParams(tps=(0.382,)),
    "TP 0.618": FibParams(tps=(0.618,)),
    "TP 1.0": FibParams(tps=(1.0,)),
    "TP 1.618": FibParams(tps=(1.618,)),
    "9 TP po 1/9 (0.236…1.618)": FibParams(tps=FIB_TPS, fractions=ALL9),
    "9 TP po 1/9 + BE po 0.382": FibParams(tps=FIB_TPS, fractions=ALL9, be_after=1),
    "3 TP (0.5/1.0/1.618) + BE po 1.": FibParams(tps=(0.5, 1.0, 1.618), fractions=(1 / 3,) * 3, be_after=0),
    "9 TP + BE + filtr trendline": FibParams(tps=FIB_TPS, fractions=ALL9, be_after=1, trend_filter=True),
    "TP 1.0 + filtr trendline": FibParams(tps=(1.0,), trend_filter=True),
    "9 TP + BE + Volume Profile": FibParams(tps=FIB_TPS, fractions=ALL9, be_after=1, vp_filter=True),
    "TP 1.0 + Volume Profile": FibParams(tps=(1.0,), vp_filter=True),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--spread", type=float, default=0.30)
    ap.add_argument("--max-hold", type=int, default=96)
    args = ap.parse_args()
    df = CSVProvider(args.csv).get_bars("XAUUSD", args.tf)
    mid = df["time"].iloc[len(df) // 2]
    print(f"{args.tf}: {len(df)} świec, {df['time'].iloc[0]:%Y-%m-%d} → {df['time'].iloc[-1]:%Y-%m-%d}, "
          f"spread ${args.spread}\n")
    rows = []
    for name, p in VARIANTS.items():
        p.max_hold = args.max_hold
        tr = find_fib_trades(df, p)
        t = pd.DataFrame([dict(time=df["time"].iloc[x.entry_idx], dir=x.direction,
                               r=x.r - args.spread / abs(x.entry - x.sl)) for x in tr if x.closed],
                         columns=["time", "dir", "r"])
        full, a, b = stats(t), stats(t[t.time < mid]), stats(t[t.time >= mid])
        rows.append({"wariant": name, **full, "1.poł R": a["sumR"], "2.poł R": b["sumR"]})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
