"""Readable chart for a zone + Fibonacci setup (used in posts)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .fibzone import FIB_TPS, FibTrade  # noqa: E402
from .structure import volume_profile  # noqa: E402

RED, GREEN, BLUE, GREY, INK = "#d32f2f", "#1b9e77", "#1e4fd8", "#757575", "#212121"
FUTURE = 30   # empty bars on the right for labels


def _trendline(vals: np.ndarray, end: int, short: int, long: int, lowest: bool):
    """TrendLineSample: extreme in [short+1, long] bars back -> extreme in [1, short] bars back."""
    pick = np.argmin if lowest else np.argmax
    x2 = end - short + int(pick(vals[end - short : end]))
    x1 = end - long + int(pick(vals[end - long : end - short]))
    return x1, vals[x1], x2, vals[x2]


def _spread_labels(ys: list[float], min_gap: float) -> list[float]:
    """Move label positions apart so they never overlap (keeps order)."""
    order = np.argsort(ys)
    out = list(ys)
    prev = -np.inf
    for i in order:
        out[i] = max(ys[i], prev + min_gap)
        prev = out[i]
    return out


def render_fib(df: pd.DataFrame, tr: FibTrade, path: Path, title: str, timeframe: str,
               lookback: int = 80, tl_short: int = 30, tl_long: int = 100, handle: str = "") -> Path:
    end = tr.entry_idx
    start = max(0, end - lookback)
    win = df.iloc[start : end + 1].copy()
    win.index = pd.DatetimeIndex(win["time"]).tz_convert(None)
    x = lambda i: i - start  # noqa: E731
    mc = mpf.make_marketcolors(up=GREEN, down=RED, edge="inherit", wick="inherit")
    fig, axes = mpf.plot(win[["open", "high", "low", "close"]], type="candle", returnfig=True, figsize=(13, 7.5),
                         style=mpf.make_mpf_style(marketcolors=mc, gridstyle="-", gridcolor="#f0f0f0",
                                                  facecolor="white", y_on_right=True,
                                                  rc={"font.size": 11, "axes.edgecolor": "#bdbdbd"}),
                         datetime_format="%d %b %H:%M", xrotation=0, tight_layout=True, ylabel="")
    ax = axes[0]
    last = len(win) - 1
    right = last + FUTURE
    ax.set_xlim(-1, right)
    buy = tr.direction == "BUY"
    rng = tr.fib1 - tr.fib0
    lvl = lambda f: tr.fib0 + f * rng  # noqa: E731

    ys = [lvl(-0.1272), lvl(1.618), win["low"].min(), win["high"].max()]
    span = max(ys) - min(ys)
    ax.set_ylim(min(ys) - span * 0.05, max(ys) + span * 0.07)
    ylim = ax.get_ylim()

    # volume profile (subtle, left side)
    prof = volume_profile(df, end, 200, bins=50)
    if prof is not None:
        mids = (prof.edges[:-1] + prof.edges[1:]) / 2
        in_va = (mids >= prof.val) & (mids <= prof.vah)
        ax.barh(mids, 16 * prof.volume / prof.volume.max(), height=(prof.edges[1] - prof.edges[0]) * 0.85,
                left=-1, color=["#b0bec5" if v else "#eceff1" for v in in_va], alpha=0.6, zorder=0)
        if ylim[0] <= prof.poc <= ylim[1]:
            ax.hlines(prof.poc, 17, last, colors="#90a4ae", lw=1, ls=(0, (5, 4)), zorder=1)
            ax.text(last, prof.poc, "POC ", color="#78909c", fontsize=9, va="bottom", ha="right", fontweight="bold")
        ax.set_ylim(ylim)

    # zone
    zc = GREEN if buy else RED
    ax.add_patch(Rectangle((-1, tr.zone_bot), right + 1, tr.zone_top - tr.zone_bot, fc=zc, alpha=0.12, ec="none",
                           zorder=0))
    ax.text(last * 0.45, (tr.zone_bot + tr.zone_top) / 2, "BUY ZONE" if buy else "SELL ZONE", color=zc,
            fontsize=11, fontweight="bold", va="center", ha="center", alpha=0.9)

    # trendlines (data up to the entry bar only)
    for vals, lowest, col in ((df["low"].to_numpy(), True, GREEN), (df["high"].to_numpy(), False, RED)):
        if end - tl_long >= 0:
            x1, y1, x2, y2 = _trendline(vals, end, tl_short, tl_long, lowest)
            k = (y2 - y1) / (x2 - x1)
            xa, xb = max(x1, start), end + FUTURE
            ax.plot([x(xa), x(xb)], [y1 + k * (xa - x1), y1 + k * (xb - x1)], color=col, lw=1.2, alpha=0.45,
                    ls="-", zorder=1)

    # fibonacci levels: lines + non-overlapping labels on the right
    fx = x(max(tr.fib1_idx, start))
    rows = []
    for f in (-0.1272, 0.0, 0.1272, *FIB_TPS):
        if f == 0.1272:
            rows.append((f, f"ENTRY  {lvl(f):.2f}", BLUE, 2.2, "-"))
        elif f == -0.1272:
            rows.append((f, f"STOP LOSS  {lvl(f):.2f}", RED, 2.2, "-"))
        elif f in FIB_TPS:
            rows.append((f, f"TP{FIB_TPS.index(f) + 1}  {lvl(f):.2f}", GREEN, 1.0, "--"))
        else:
            rows.append((f, f"0  {lvl(f):.2f}", GREY, 0.8, ":"))
    label_y = _spread_labels([lvl(f) for f, *_ in rows], span * 0.045)
    for (f, text, col, lw, ls), ly in zip(rows, label_y):
        y = lvl(f)
        ax.hlines(y, fx, last + 6, colors=col, lw=lw, ls=ls, zorder=3)
        ax.plot([last + 6, last + 9], [y, ly], color=col, lw=0.8, zorder=3)
        ax.text(last + 9.5, ly, text, color="white", fontsize=10, va="center", ha="left", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc=col, ec=col), zorder=6)

    # summary box
    entry = lvl(0.1272)
    r1 = entry + (entry - tr.sl)
    box = (f"{tr.direction} STOP   {title} {timeframe}\n"
           f"Entry {entry:.2f}   SL {tr.sl:.2f}\n"
           f"1:1 RR at {r1:.2f}   TP9 {lvl(1.618):.2f}")
    ax.text(0.01, 0.98, box, transform=ax.transAxes, fontsize=11, va="top", ha="left", color=INK,
            family="monospace", bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#bdbdbd", alpha=0.95), zorder=7)

    ax.set_title(f"{title} · {timeframe} · {tr.direction} STOP — zone bounce + Fibonacci", loc="left",
                 fontsize=14, fontweight="bold", color=INK)
    if handle:
        ax.text(0.5, 0.45, handle, transform=ax.transAxes, fontsize=40, color="#000000", alpha=0.05,
                ha="center", va="center", fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return path
