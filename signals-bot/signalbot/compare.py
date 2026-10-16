"""Porównanie wariantów strategii na tej samej historii.

    python -m signalbot.compare data/XAUUSD_30m.csv --tf M30

Wyniki liczone osobno dla pierwszej i drugiej połowy danych — wariant, który działa
tylko w jednej połowie, najpewniej jest dopasowany do szumu.
"""
from __future__ import annotations

import argparse
from dataclasses import replace

import pandas as pd

from .data import CSVProvider
from .strategy import Params, find_setups
from .tracker import evaluate

VARIANTS = {
    "A bazowy (BOS/CHOCH + retest)": Params(),
    "B + wymagane Fibo 0.5–0.786": Params(require=("fibo",)),
    "C + wymagane FVG": Params(require=("fvg",)),
    "D + wymagany sweep płynności": Params(require=("sweep",)),
    "E min. 1 konfluencja": Params(min_score=1),
    "F min. 2 konfluencje": Params(min_score=2),
    "G bazowy, TP na płynności": Params(tp_mode="liquidity"),
    "H min. 1 konfl. + TP płynność": Params(min_score=1, tp_mode="liquidity"),
}


def trades(df: pd.DataFrame, p: Params, spread: float, max_hold: int) -> pd.DataFrame:
    rows = []
    for s in find_setups(df, p):
        res = evaluate(df.iloc[s.confirm_idx + 1 :], s.direction, s.entry, s.sl, s.tp, max_hold)
        if res is None:
            continue
        risk = abs(s.sl - s.entry)
        rows.append(dict(time=s.confirm_time, dir=s.direction, r=res.r - spread / risk,
                         outcome=res.outcome, score=s.score))
    return pd.DataFrame(rows, columns=["time", "dir", "r", "outcome", "score"])


def stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return dict(n=0, win="-", sumR=0.0, avgR=0.0, PF="-", DD=0.0)
    eq = t["r"].cumsum()
    gains, losses = t.loc[t.r > 0, "r"].sum(), -t.loc[t.r < 0, "r"].sum()
    return dict(n=len(t), win=f"{(t.r > 0).mean():.0%}", sumR=round(t.r.sum(), 1),
                avgR=round(t.r.mean(), 2), PF=round(gains / losses, 2) if losses else "∞",
                DD=round((eq - eq.cummax()).min(), 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tf", default="M30")
    ap.add_argument("--spread", type=float, default=0.30, help="koszt w $ na transakcję")
    ap.add_argument("--max-hold", type=int, default=96)
    args = ap.parse_args()

    df = CSVProvider(args.csv).get_bars("XAUUSD", args.tf)
    mid = df["time"].iloc[len(df) // 2]
    print(f"{args.tf}: {len(df)} świec, {df['time'].iloc[0]:%Y-%m-%d} → {df['time'].iloc[-1]:%Y-%m-%d}"
          f", podział {mid:%Y-%m-%d}, spread ${args.spread}\n")
    rows = []
    for name, p in VARIANTS.items():
        t = trades(df, p, args.spread, args.max_hold)
        full, a, b = stats(t), stats(t[t.time < mid]), stats(t[t.time >= mid])
        rows.append({"wariant": name, **full, "1.poł R": a["sumR"], "1.poł n": a["n"],
                     "2.poł R": b["sumR"], "2.poł n": b["n"]})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
